#!/usr/bin/env python3
"""WTT/TTC "WINNER" popup (EA's "contact us to determine your prize
eligibility"), in libRealRacing3.so (v14.0.1, arm64, develified build).
Issue #596. Project Real Resurrection; not affiliated with, endorsed or
supported by Electronic Arts.

The notification builder (0xd4cd44) adds one "Winner - [competitionName]"
notification (type 0x13) for every event id in the LTS prize list (LTS
+0xa8, filled only by subsync 10781). Opening it builds the popup (0xabf230)
whose CONTACT US NOW button opens a URL (0xabfa0c -> 0x1cbc61c). CC v5.76
lists every WTT a member has a time in (the same list gates the gold), so
every participant gets the popup.

Parts (default: both):
- link: the button's default URL (C string at 0x3daea9, 79-byte slot:
  EA's Winner-Instructions PDF, 78 characters + NUL) becomes LINK_URL,
  NUL-padded to the end of the slot. 0x3daef8 (the next string) is not
  touched. A `TTC_WinnerURL` server variable (10712) would still win.
- hide: no winner notification. 0xd4cf18 `b.eq 0xd4cf48` (skip the loop
  when the list is empty) becomes `b 0xd4cf48`, so the loop that adds the
  type-0x13 notifications never runs. The prize list itself, and with it
  the gold, is unchanged.

  0xd4cf18  b.eq 0xd4cf48  -> b 0xd4cf48    (54000180 -> 1400000c)

Usage:
  rr3_wtt_winner_popup.py check LIB
  rr3_wtt_winner_popup.py patch IN OUT [--parts link,hide] [--restore]
IN may be gzipped; OUT is written uncompressed (or gzipped if it ends in .gz).
"""
import argparse
import gzip
import struct
import sys

LINK_URL = b"https://www.youtube.com/watch?v=dQw4w9WgXcQ"
LINK_AT, LINK_SLOT = 0x3DAEA9, 79                       # 0x3daea9..0x3daef7
LINK_DEVELIFIED = b"https://media.contentapi.ea.com/content/dam/eacom/APAC/Winner-Instructions.pdf\0"
LINK_PATCHED = LINK_URL.ljust(LINK_SLOT, b"\0")

HIDE_AT, HIDE_DEVELIFIED, HIDE_PATCHED = 0xD4CF18, 0x54000180, 0x1400000C   # b.eq / b 0xd4cf48

PARTS = ("link", "hide")
assert len(LINK_DEVELIFIED) == LINK_SLOT and len(LINK_URL) < LINK_SLOT


def load(path):
    data = open(path, "rb").read()
    return bytearray(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def part_state(d, part):
    """0 develified, 1 patched, None unrecognised."""
    if part == "link":
        got = bytes(d[LINK_AT:LINK_AT + LINK_SLOT])
        return {LINK_DEVELIFIED: 0, LINK_PATCHED: 1}.get(got)
    got = struct.unpack_from("<I", d, HIDE_AT)[0]
    return {HIDE_DEVELIFIED: 0, HIDE_PATCHED: 1}.get(got)


def write_part(d, part, on):
    if part == "link":
        d[LINK_AT:LINK_AT + LINK_SLOT] = LINK_PATCHED if on else LINK_DEVELIFIED
    else:
        struct.pack_into("<I", d, HIDE_AT, HIDE_PATCHED if on else HIDE_DEVELIFIED)


def contents(d):
    """`patches` entry for rr3_build.py: '' develified, None unrecognised.
    e.g. wtt-winner=link+hide (only revisions carry @vN)."""
    st = {p: part_state(d, p) for p in PARTS}
    if None in st.values():
        return None
    on = [p for p in PARTS if st[p]]
    return "wtt-winner=" + "+".join(on) if on else ""


def describe(d):
    return {p: {0: "develified", 1: "patched"}.get(part_state(d, p), "unrecognised") for p in PARTS}


def parse_parts(s):
    parts = [p for p in s.split(",") if p]
    bad = [p for p in parts if p not in PARTS]
    if bad or not parts:
        sys.exit(f"--parts: choose from {', '.join(PARTS)}")
    return parts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("lib")
    p = sub.add_parser("patch")
    p.add_argument("inp")
    p.add_argument("out")
    p.add_argument("--parts", default=",".join(PARTS), help="comma-separated: link, hide (default both)")
    p.add_argument("--restore", action="store_true", help="put the develified bytes of these parts back")
    a = ap.parse_args()

    d = load(a.lib if a.cmd == "check" else a.inp)
    st = describe(d)
    if a.cmd == "check":
        for part, s in st.items():
            print(f"{part}: {s}")
        return
    parts = parse_parts(a.parts)
    bad = [x for x in parts if st[x] == "unrecognised"]
    if bad:
        sys.exit(f"unexpected bytes for {', '.join(bad)}: not the v14.0.1 develified build?")
    for part in parts:
        write_part(d, part, not a.restore)
    out = gzip.compress(bytes(d)) if a.out.endswith(".gz") else bytes(d)
    open(a.out, "wb").write(out)
    print(f"{a.out}: " + ", ".join(f"{k} {v}" for k, v in describe(d).items()))


if __name__ == "__main__":
    main()
