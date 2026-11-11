#!/usr/bin/env python3
"""Race Selector: a Time Trial best per track and car (issues #48, #106),
by patching libRealRacing3.so (v14.0.1, arm64, develified build). NOT TESTED IN
GAME. Guide: docs/race-selector-times.md.

Every Debug Race Selector race reuses debug event 18130, and the game keeps
one result record (best time, 56 bytes) per event, so all tracks and cars
share it. This patch keeps event 18130 but gives it the record of the
picked track and car:

  0x9f5dc8   selector start, `bl 0x135a844` (start the event) -> `bl 0x1ac0c40`
             (sel_start). Before starting, sel_start keeps event 18130's
             current record in our own file files/doc/race_selector_times.dat
             under the track and car it belongs to, then puts the record
             stored for the new track and car into event 18130 (or the
             "never raced" state of rr3_events.py reset), then starts the
             race as before. The game's saves only ever hold the record of
             the last selector race, as without the patch.
  0x1ac0c40  new code (780 bytes, tools/asm/rr3_selector_times.s) in the zero
             padding before 0x1ac1000, after the Time Trial `best` code of
             rr3_tt_laps.py (0x1ac0b40..0x1ac0be8).

Versions (`check` knows both, `patch` writes the latest):
  v2  car = the player's current car id (garage index game+0xcd8, car
      instance +0x40). File version 2.
  v1  car key = the start call's third argument, which is the player's skill,
      not a car, so all cars on a track shared one best (issue #106). Also
      patched 0x1024c98 and 0x137cb64 to rename tt_replay files per track;
      those are the ghost owner's livery files, not ghosts, and the change
      never applied. File version 1. `--version 1` writes it, for testing.

File format (little-endian): "RRST", version, entry count, track and car of
the record now in event 18130 (-1 = none), 12 reserved bytes, then 64-byte
entries: track id, car id (v1: skill), the 56-byte record (best time ms at
record +8). Up to 1024 entries. v2 doesn't read a version 1 file: it starts
empty and overwrites it.

Usage:
  rr3_selector_times.py check LIB
  rr3_selector_times.py patch IN OUT [--version 1|2] [--restore]
  rr3_selector_times.py list FILE          (a race_selector_times.dat)
IN may be develified or carry either version (it is replaced); it may be
gzipped. OUT is written uncompressed (or gzipped if it ends in .gz).
"""
import argparse
import gzip
import struct
import sys

CAVE = 0x1AC0C40
# tools/asm/rr3_selector_times.s linked for 0x1ac0c40 (build line in that file).
CODE_V2 = (
    0xA9AA7BFD, 0x910003FD, 0xA90153F3, 0xA9025BF5, 0xA90363F7, 0xA9046BF9,
    0xA90573FB, 0xAA0003F3, 0xAA0103F4, 0x2A0203F5, 0xB9400288, 0x5288DA49,
    0x6B09011F, 0x54001041, 0xB0002568, 0xF942ED08, 0xF9400108, 0xB98CD909,
    0x37F80FA9, 0xF945750A, 0xF945790B, 0xD280030C, 0x9B0C292A, 0xEB0B015F,
    0x54000EE2, 0xF940014A, 0xB4000EAA, 0xB940415B, 0x91002280, 0x97BB43F6,
    0x2A0003F6, 0xB0002568, 0xF942ED08, 0xF9400108, 0x9111E100, 0x97E9B3E5,
    0xAA1403E1, 0x97BBEAA3, 0xAA0003F7, 0xD2800400, 0xF2A00020, 0x940D5FAF,
    0xB4000CA0, 0xAA0003F8, 0x910183E0, 0x94000083, 0x910183E0, 0x10001181,
    0x940D5BF8, 0xD280001A, 0xB4000160, 0xAA0003F9, 0xAA1803E0, 0xD2800021,
    0xD2800402, 0xF2A00022, 0xAA1903E3, 0x940D5C5F, 0xAA0003FA, 0xAA1903E0,
    0x940D5BF0, 0xF100835F, 0x5400020B, 0xB9400308, 0x528A4A49, 0x72AA8A69,
    0x6B09011F, 0x54000161, 0xB9400708, 0x7100091F, 0x54000101, 0xB9400B08,
    0x7110011F, 0x540000A8, 0xD2800409, 0x8B081929, 0xEB09035F, 0x5400018A,
    0x528A4A49, 0x72AA8A69, 0xB9000309, 0x52800049, 0xB9000709, 0xB9000B1F,
    0x12800009, 0xB9000F09, 0xB9001309, 0xB900171F, 0xF9000F1F, 0xB4000497,
    0xB9400F01, 0x37F80241, 0xB9401302, 0xAA1803E0, 0x9400003B, 0xB5000160,
    0xB9400B08, 0x7110011F, 0x54000162, 0x11000509, 0xB9000B09, 0x91008300,
    0x8B081800, 0xB9400F01, 0xB9401302, 0x29000801, 0x91002000, 0xAA1703E1,
    0x9400003B, 0xAA1803E0, 0x2A1603E1, 0x2A1B03E2, 0x94000029, 0xB40000A0,
    0x91002001, 0xAA1703E0, 0x94000033, 0x14000008, 0xB90002FF, 0xB9000AFF,
    0xB9000EFF, 0xB90012FF, 0x3900C6FF, 0x52800028, 0x3900CAE8, 0xB9000F16,
    0xB900131B, 0x910183E0, 0x70000761, 0x940D5BA7, 0xB4000160, 0xAA0003F9,
    0xB9400B08, 0xD2800402, 0x8B081842, 0xAA1803E0, 0xD2800021, 0xAA1903E3,
    0x940D5BC6, 0xAA1903E0, 0x940D5BA0, 0xAA1803E0, 0x940D5CEA, 0xAA1303E0,
    0xAA1403E1, 0x2A1503E2, 0xA94153F3, 0xA9425BF5, 0xA94363F7, 0xA9446BF9,
    0xA94573FB, 0xA8D67BFD, 0x17E26669, 0xB9400808, 0x91008009, 0xD2800000,
    0x34000148, 0x29402D2A, 0x6B01015F, 0x7A420160, 0x54000061, 0xAA0903E0,
    0xD65F03C0, 0x91010129, 0x51000508, 0x17FFFFF7, 0xD65F03C0, 0xA9402428,
    0xA9002408, 0xA9412428, 0xA9012408, 0xA9422428, 0xA9022408, 0xF9401828,
    0xF9001808, 0xD65F03C0, 0xA9BE7BFD, 0x910003FD, 0xF9000BE0, 0x97DF9239,
    0xAA0003E3, 0xF9400BE0, 0xD2802001, 0x500000A2, 0x940D6244, 0xA8C27BFD,
    0xD65F03C0, 0x77006272, 0x73250062, 0x65636172, 0x6C65735F, 0x6F746365,
    0x69745F72, 0x2E73656D, 0x00746164,
)
SITES_V2 = [
    (0x9F5DC8, 0x9425929F, 0x94432B9E),   # bl 0x135a844 -> bl 0x1ac0c40 (sel_start)
]
# v1: the same file at git commit cddab6c (tools/asm/rr3_selector_times.s).
CODE_V1 = (
    0xA9AB7BFD, 0x910003FD, 0xA90153F3, 0xA9025BF5, 0xA90363F7, 0xA9046BF9,
    0xAA0003F3, 0xAA0103F4, 0x2A0203F5, 0xB9400288, 0x5288DA49, 0x6B09011F,
    0x54000E81, 0x91002280, 0x97BB4405, 0x2A0003F6, 0xB0002568, 0xF942ED08,
    0xF9400108, 0x9111E100, 0x97E9B3F4, 0xAA1403E1, 0x97BBEAB2, 0xAA0003F7,
    0xD2800400, 0xF2A00020, 0x940D5FBE, 0xB4000CA0, 0xAA0003F8, 0x910143E0,
    0x94000082, 0x910143E0, 0x10001661, 0x940D5C07, 0xD280001A, 0xB4000160,
    0xAA0003F9, 0xAA1803E0, 0xD2800021, 0xD2800402, 0xF2A00022, 0xAA1903E3,
    0x940D5C6E, 0xAA0003FA, 0xAA1903E0, 0x940D5BFF, 0xF100835F, 0x5400020B,
    0xB9400308, 0x528A4A49, 0x72AA8A69, 0x6B09011F, 0x54000161, 0xB9400708,
    0x7100051F, 0x54000101, 0xB9400B08, 0x7110011F, 0x540000A8, 0xD2800409,
    0x8B081929, 0xEB09035F, 0x5400018A, 0x528A4A49, 0x72AA8A69, 0xB9000309,
    0x52800029, 0xB9000709, 0xB9000B1F, 0x12800009, 0xB9000F09, 0xB9001309,
    0xB900171F, 0xF9000F1F, 0xB4000497, 0xB9400F01, 0x37F80241, 0xB9401302,
    0xAA1803E0, 0x9400003A, 0xB5000160, 0xB9400B08, 0x7110011F, 0x54000162,
    0x11000509, 0xB9000B09, 0x91008300, 0x8B081800, 0xB9400F01, 0xB9401302,
    0x29000801, 0x91002000, 0xAA1703E1, 0x9400003A, 0xAA1803E0, 0x2A1603E1,
    0x2A1503E2, 0x94000028, 0xB40000A0, 0x91002001, 0xAA1703E0, 0x94000032,
    0x14000008, 0xB90002FF, 0xB9000AFF, 0xB9000EFF, 0xB90012FF, 0x3900C6FF,
    0x52800028, 0x3900CAE8, 0xB9000F16, 0xB9001315, 0x910143E0, 0x70000C41,
    0x940D5BB6, 0xB4000160, 0xAA0003F9, 0xB9400B08, 0xD2800402, 0x8B081842,
    0xAA1803E0, 0xD2800021, 0xAA1903E3, 0x940D5BD5, 0xAA1903E0, 0x940D5BAF,
    0xAA1803E0, 0x940D5CF9, 0xAA1303E0, 0xAA1403E1, 0x2A1503E2, 0xA94153F3,
    0xA9425BF5, 0xA94363F7, 0xA9446BF9, 0xA8D57BFD, 0x17E26679, 0xB9400808,
    0x91008009, 0xD2800000, 0x34000148, 0x29402D2A, 0x6B01015F, 0x7A420160,
    0x54000061, 0xAA0903E0, 0xD65F03C0, 0x91010129, 0x51000508, 0x17FFFFF7,
    0xD65F03C0, 0xA9402428, 0xA9002408, 0xA9412428, 0xA9012408, 0xA9422428,
    0xA9022408, 0xF9401828, 0xF9001808, 0xD65F03C0, 0xA9BE7BFD, 0x910003FD,
    0xF9000BE0, 0x97DF9249, 0xAA0003E3, 0xF9400BE0, 0xD2802001, 0x500005A2,
    0x940D6254, 0xA8C27BFD, 0xD65F03C0, 0xB9400281, 0x14000002, 0xB9402A81,
    0x5288DA49, 0x6B09001F, 0x54000161, 0xA9BE7BFD, 0x910003FD, 0xA90107E0,
    0x94000008, 0x2A0003E2, 0xA94107E0, 0xA8C27BFD, 0x37F80062, 0x12003842,
    0x2A024021, 0xD65F03C0, 0xA9BF7BFD, 0x910003FD, 0xB0002568, 0xF942ED08,
    0xF9400108, 0x5281B509, 0x72A00029, 0x8B090100, 0x5284E161, 0x97C6DDD9,
    0xB4000140, 0x2A1F03E1, 0x97C6AAB9, 0xB40000E0, 0x2A1F03E1, 0x97C6B894,
    0xB4000080, 0x91002000, 0x97BB4345, 0x14000002, 0x12800000, 0xA8C17BFD,
    0xD65F03C0, 0x77006272, 0x73250062, 0x65636172, 0x6C65735F, 0x6F746365,
    0x69745F72, 0x2E73656D, 0x00746164,
)
# (site, develified word, patched word); .text VMA == file offset in this build
SITES_V1 = [
    (0x9F5DC8, 0x9425929F, 0x94432B9E),   # bl 0x135a844 -> bl 0x1ac0c40 (sel_start)
    (0x1024C98, 0xB9400281, 0x942A7095),  # ldr w1, [x20] -> bl 0x1ac0eec (ghost_key1)
    (0x137CB64, 0xB9402A81, 0x941D10E4),  # ldr w1, [x20, #0x28] -> bl 0x1ac0ef4 (ghost_key2)
]
VERSIONS = {1: (CODE_V1, SITES_V1), 2: (CODE_V2, SITES_V2)}
LATEST = 2
CAVE_MAX = max(len(c) for c, _ in VERSIONS.values())
# every site any version writes, with its develified word
DEVELIFIED_SITES = {site: develified for _, sites in VERSIONS.values() for site, develified, _ in sites}
EVENT = 18130


def load(path):
    data = open(path, "rb").read()
    return bytearray(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def state(d):
    """'develified', 'v1', 'v2', or None (unrecognised)."""
    cave = struct.unpack_from(f"<{CAVE_MAX}I", d, CAVE)
    words = {site: struct.unpack_from("<I", d, site)[0] for site in DEVELIFIED_SITES}
    if not any(cave) and all(words[s] == w for s, w in DEVELIFIED_SITES.items()):
        return "develified"
    for v, (code, sites) in VERSIONS.items():
        rest = {s: w for s, w in DEVELIFIED_SITES.items() if s not in {x for x, _, _ in sites}}
        if (cave[:len(code)] == code and not any(cave[len(code):])
                and all(words[s] == p for s, _, p in sites)
                and all(words[s] == w for s, w in rest.items())):
            return f"v{v}"
    return None


def describe(s):
    return {"develified": "develified", "v1": "patched v1 (old: car key is the player skill)",
            "v2": "patched v2 (Race Selector best per track and car)"}[s]


def contents(d):
    """`patches` entry for rr3_build.py: '' develified, None unrecognised."""
    s = state(d)
    return None if s is None else "" if s == "develified" else "selector-times" if s == "v1" else "selector-times@" + s


def list_file(path):
    b = open(path, "rb").read()
    if len(b) < 32 or b[:4] != b"RRST":
        sys.exit("not a race_selector_times.dat file")
    ver, n, track, car = struct.unpack_from("<Iiii", b, 4)
    what = "car id" if ver >= 2 else "car key (v1: player skill)"
    print(f"version {ver}, {n} entries; event {EVENT} now holds track {track}, {what} {car}")
    print("track  car     best ms  best (m:ss.mmm)  best result")
    for i in range(n):
        o = 32 + 64 * i
        if o + 64 > len(b):
            sys.exit("file is cut short")
        t, c, res, _codrv, best = struct.unpack_from("<iiiii", b, o)
        shown = f"{best // 60000}:{best // 1000 % 60:02}.{best % 1000:03}" if best > 0 else "-"
        print(f"{t:5}  {c:7}  {best:7}  {shown:>15}  {res:11}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").add_argument("lib")
    p = sub.add_parser("patch")
    p.add_argument("inp")
    p.add_argument("out")
    p.add_argument("--version", type=int, choices=sorted(VERSIONS), default=LATEST,
                   help=f"code version to write (default: latest, {LATEST})")
    p.add_argument("--restore", action="store_true", help="put the develified bytes back")
    sub.add_parser("list").add_argument("file")
    a = ap.parse_args()

    if a.cmd == "list":
        list_file(a.file)
        return
    d = load(a.lib if a.cmd == "check" else a.inp)
    s = state(d)
    if s is None:
        sys.exit("unexpected bytes at a patch site or in the code area: not the v14.0.1 develified build?")
    if a.cmd == "check":
        print(describe(s))
        return
    d[CAVE:CAVE + 4 * CAVE_MAX] = bytes(4 * CAVE_MAX)
    for site, develified in DEVELIFIED_SITES.items():
        struct.pack_into("<I", d, site, develified)
    if not a.restore:
        code, sites = VERSIONS[a.version]
        struct.pack_into(f"<{len(code)}I", d, CAVE, *code)
        for site, _, patch in sites:
            struct.pack_into("<I", d, site, patch)
    open(a.out, "wb").write(gzip.compress(bytes(d)) if a.out.endswith(".gz") else bytes(d))
    print(f"{a.out}: {describe(state(d))}")


if __name__ == "__main__":
    main()
