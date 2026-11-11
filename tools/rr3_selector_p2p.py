#!/usr/bin/env python3
"""Race Selector P2P mode: phones meet only with the same track (v1) and
the same laps (v2), in libRealRacing3.so (v14.0.1, arm64, develified
build). Issue #469.

The Debug Race Selector's P2P mode (GAMETEXT_P2P, mode 24) starts online
matchmaking (0x9f5664: the picked track goes into the track holder at
GOT 0x1f6dc20, then 0xf76084). The join (message 36, 0xbb1e80) carries an
event that MP uses as the room key. Both event builders (0xf761a0,
0xf766ac) compute

    event = ([omp+0x4c8] % 10) * 1000 + env * 100 + [mp+0x120]

where [omp+0x4c8] is the OMP race slot and mp = [[game+0x54c0]+0x188].
The selector has no slot (-1), and nothing sets [mp+0x120] for it, so the
event is -1000 plus whatever was left there: two phones meet only when
their leftovers are equal, whatever track each picked (mp.log 2026-11-08:
-1000, -1029, -1717590329). At race start, each phone overrides CC's
StartMatch track with its own pick (0xf7add4) and takes CC's laps
(0xf7aeec); the selector's lap slider is greyed out in P2P mode
(0x9f63c0) and its value is never read.

v2 (`selector-p2p@v2`, default), the lib part of design B in #469:

1. the lap slider is enabled in P2P mode (both selector UIs);
2. P2P start copies the slider's laps into [mp+0x120] (read just after
   by the event builder, inside the same call);
3. when the slot is negative, the builders use
   -(track * 4096 + (laps & 0xff) * 16) instead of [mp+0x120], so the
   event is -1000 - 4096 * track - 16 * laps (env 0 on our hosts): same
   track and laps, same room; any difference is at least 16 apart, so
   MP's event +-1 merge (#280) can't join them. OMP races (slot >= 0) are
   unchanged.

MP (v0.26) decodes track and laps from such an event and CC (v5.59)
answers the room's StartMatch with them (unranked); without those server
changes the race still runs CC's laps.

  0xf76210  ldr w20, [x8, #0x120]    -> bl 0x1bb4c88  (A, slot in x9)
  0xf766f8  ldr w26, [x22, #0x120]   -> bl 0x1bb4ccc  (B, slot in x27)
  0x9f63c0  strh wzr, [x0, #0x20]    -> b  0x1c117b0  (C, screen UI, leaf)
  0x9f64f4  strh wzr, [x19, #0x28]   -> b  0x1c117c0  (D, ImGui UI)
  0x9f5678  add x0, x8, #0xa50       -> bl 0x1c117d0  (E, P2P start)

A (17 instructions)                    B (13)
  ldr  w20, [x8, #0x120]   original      ldr  w26, [x22, #0x120]
  tbnz x9, #63, sel        slot < 0      tbnz x27, #63, sel
  ret                                    ret
sel: stp x29, x30, [sp, #-48]!         sel: stp x29, x30, [sp, #-16]!
  stp  x9, x10, [sp, #16]  live here     adrp x0, 0x1f6d000
  str  x11, [sp, #32]                    ldr  x0, [x0, #0xc20]
  adrp x0, 0x1f6d000                     bl   0x991c8c
  ldr  x0, [x0, #0xc20]    track holder  and  w26, w26, #0xff
  bl   0x991c8c            track id      lsl  w26, w26, #4
  and  w20, w20, #0xff     laps          add  w26, w26, w0, lsl #12
  lsl  w20, w20, #4                      neg  w26, w26
  add  w20, w20, w0, lsl #12             ldp  x29, x30, [sp], #16
  neg  w20, w20                          ret
  ldp  x9, x10, [sp, #16]
  ldr  x11, [sp, #32]
  ldp  x29, x30, [sp], #48
  ret

C (4)                       D (4)                       E (6)
  cmp  w8, #0x18              cmp  w8, #0x18              ldr  w9, [x0, #0x10]       slider laps
  cset w9, eq                 cset w9, eq                 ldr  x10, [x8, #0x54c0]
  strh w9, [x0, #0x20]        strh w9, [x19, #0x28]       ldr  x10, [x10, #0x188]    mp
  b    0x9f63c4               b    0x9f64f8               str  w9, [x10, #0x120]
                                                          add  x0, x8, #0xa50        original
                                                          ret

C/D: the mode's "laps slider on" byte (+0x20 / +0x28) is 1 for mode 24
(0x18), 0 for every other mode that reaches the site, as before; the
second byte (the other slider) stays 0. w9 is written before it is read
on every path after both sites. 0x9f636c is a leaf, so C is entered
with b, not bl. E: x0 = the selector (`this` = screen+0x288, laps at
+0x10), x8 = game; x9, x10 are dead (0x9f567c calls). x20 and x26 are
callee-saved, so the laps survive the call to 0x991c8c.

v1 (`selector-p2p`, `--version 1`): the track only, -(track * 1024),
caves A1/B1 at 0x1bb4c88/0x1bb4cc0 (96 bytes); no C, D, E. `check`
still recognises it.

Caves (tables/lib-code-caves.csv, no requires): 0x1bb4c88 (zero padding
before the SM4 S-box, 120 bytes: A + B) and 0x1c117b0 (zero padding,
80 bytes: C + D + E, 56 bytes).

Usage:
  rr3_selector_p2p.py check LIB
  rr3_selector_p2p.py patch IN OUT [--version 1|2] [--restore]
IN may be gzipped; OUT is written uncompressed (or gzipped if it ends in .gz).
"""
import argparse
import gzip
import struct
import sys

VERSION = 2
REQUIRES = []                         # neither cave needs anything switched off first

SITE_A, SITE_A_DEVELIFIED = 0xF76210, 0xB9412114      # ldr w20, [x8, #0x120]
SITE_B, SITE_B_DEVELIFIED = 0xF766F8, 0xB94122DA      # ldr w26, [x22, #0x120]
SITE_C, SITE_C_DEVELIFIED = 0x9F63C0, 0x7900401F      # strh wzr, [x0, #0x20]
SITE_D, SITE_D_DEVELIFIED = 0x9F64F4, 0x7900527F      # strh wzr, [x19, #0x28]
SITE_E, SITE_E_DEVELIFIED = 0x9F5678, 0x91294100      # add x0, x8, #0xa50
CAVE = 0x1BB4C88                      # zero padding up to the SM4 S-box at 0x1bb4d00
CAVE_END = 0x1BB4D00
CAVE2 = 0x1C117B0                     # zero padding up to a constant table at 0x1c11800 (v2)
CAVE2_END = 0x1C11800
TRACK_ID = 0x991C8C                   # track id of a track holder (as at 0xf7addc)
GOT_TRACK = 0x1F6DC20                 # GOT entry: the selector's track holder
P2P_MODE = 0x18                       # GAMETEXT_P2P in the selector's mode table

RET = 0xD65F03C0


def bl(at, to):
    return 0x94000000 | (((to - at) >> 2) & 0x3FFFFFF)


def b(at, to):
    return 0x14000000 | (((to - at) >> 2) & 0x3FFFFFF)


def adrp(rd, at, to):
    imm = (to >> 12) - (at >> 12)
    return 0x90000000 | ((imm & 3) << 29) | (((imm >> 2) & 0x7FFFF) << 5) | rd


def ldr_x0_got(off):
    return 0xF9400000 | ((off >> 3) << 10)                   # ldr x0, [x0, #off]


def tbnz63(rt, skip):
    return 0xB7F80000 | (skip << 5) | rt                     # tbnz xRT, #63, +skip*4


# --- v1: the track only ----------------------------------------------------------
A1, B1 = CAVE, CAVE + 14 * 4


def cave_a1():
    a = lambda i: A1 + 4 * i                                 # noqa: E731
    return [SITE_A_DEVELIFIED, tbnz63(9, 2), RET,
            0xA9BD7BFD, 0xA9012BE9, 0xF90013EB,              # stp x29, x30 / stp x9, x10 / str x11
            adrp(0, a(6), GOT_TRACK), ldr_x0_got(GOT_TRACK & 0xFFF), bl(a(8), TRACK_ID),
            0x4B002BF4,                                      # neg w20, w0, lsl #10
            0xA9412BE9, 0xF94013EB, 0xA8C37BFD, RET]


def cave_b1():
    a = lambda i: B1 + 4 * i                                 # noqa: E731
    return [SITE_B_DEVELIFIED, tbnz63(27, 2), RET,
            0xA9BF7BFD,                                      # stp x29, x30, [sp, #-16]!
            adrp(0, a(4), GOT_TRACK), ldr_x0_got(GOT_TRACK & 0xFFF), bl(a(6), TRACK_ID),
            0x4B002BFA,                                      # neg w26, w0, lsl #10
            0xA8C17BFD, RET]


# --- v2: track and laps ----------------------------------------------------------
A2, B2 = CAVE, CAVE + 17 * 4
C2, D2, E2 = CAVE2, CAVE2 + 4 * 4, CAVE2 + 8 * 4


def cave_a2():
    a = lambda i: A2 + 4 * i                                 # noqa: E731
    return [
        SITE_A_DEVELIFIED,                                   # 0  ldr  w20, [x8, #0x120]  (laps, v2)
        tbnz63(9, 2),                                        # 1  tbnz x9, #63, sel
        RET,                                                 # 2  ret
        0xA9BD7BFD,                                          # 3  sel: stp x29, x30, [sp, #-48]!
        0xA9012BE9,                                          # 4  stp x9, x10, [sp, #16]
        0xF90013EB,                                          # 5  str x11, [sp, #32]
        adrp(0, a(6), GOT_TRACK),                            # 6  adrp x0, GOT page
        ldr_x0_got(GOT_TRACK & 0xFFF),                       # 7  ldr x0, [x0, #0xc20]
        bl(a(8), TRACK_ID),                                  # 8  bl 0x991c8c
        0x12001E94,                                          # 9  and w20, w20, #0xff
        0x531C6E94,                                          # 10 lsl w20, w20, #4
        0x0B003294,                                          # 11 add w20, w20, w0, lsl #12
        0x4B1403F4,                                          # 12 neg w20, w20
        0xA9412BE9,                                          # 13 ldp x9, x10, [sp, #16]
        0xF94013EB,                                          # 14 ldr x11, [sp, #32]
        0xA8C37BFD,                                          # 15 ldp x29, x30, [sp], #48
        RET,                                                 # 16 ret
    ]


def cave_b2():
    a = lambda i: B2 + 4 * i                                 # noqa: E731
    return [
        SITE_B_DEVELIFIED,                                   # 0  ldr  w26, [x22, #0x120]
        tbnz63(27, 2),                                       # 1  tbnz x27, #63, sel
        RET,                                                 # 2  ret
        0xA9BF7BFD,                                          # 3  sel: stp x29, x30, [sp, #-16]!
        adrp(0, a(4), GOT_TRACK),                            # 4  adrp x0, GOT page
        ldr_x0_got(GOT_TRACK & 0xFFF),                       # 5  ldr x0, [x0, #0xc20]
        bl(a(6), TRACK_ID),                                  # 6  bl 0x991c8c
        0x12001F5A,                                          # 7  and w26, w26, #0xff
        0x531C6F5A,                                          # 8  lsl w26, w26, #4
        0x0B00335A,                                          # 9  add w26, w26, w0, lsl #12
        0x4B1A03FA,                                          # 10 neg w26, w26
        0xA8C17BFD,                                          # 11 ldp x29, x30, [sp], #16
        RET,                                                 # 12 ret
    ]


def cave_c2():
    return [0x7100611F,                                      # cmp  w8, #0x18
            0x1A9F17E9,                                      # cset w9, eq
            0x79004009,                                      # strh w9, [x0, #0x20]
            b(C2 + 12, SITE_C + 4)]                          # b    0x9f63c4


def cave_d2():
    return [0x7100611F,                                      # cmp  w8, #0x18
            0x1A9F17E9,                                      # cset w9, eq
            0x79005269,                                      # strh w9, [x19, #0x28]
            b(D2 + 12, SITE_D + 4)]                          # b    0x9f64f8


def cave_e2():
    return [0xB9401009,                                      # ldr  w9, [x0, #0x10]       slider laps
            0xF96A610A,                                      # ldr  x10, [x8, #0x54c0]
            0xF940C54A,                                      # ldr  x10, [x10, #0x188]    mp
            0xB9012149,                                      # str  w9, [x10, #0x120]
            SITE_E_DEVELIFIED,                               # add  x0, x8, #0xa50
            RET]


def pack(words):
    return struct.pack(f"<{len(words)}I", *words)


CAVE_LEN = 4 * (17 + 13)                                     # the larger use of cave 1 (v2)
CAVE2_LEN = 4 * (4 + 4 + 6)
assert CAVE + CAVE_LEN <= CAVE_END and CAVE2 + CAVE2_LEN <= CAVE2_END
assert len(cave_a1() + cave_b1()) == 24 and len(cave_a2()) == 17 and len(cave_b2()) == 13


def image(version):
    """{site: word} and the two cave byte strings for develified (0) or a version."""
    if version == 0:
        sites = {SITE_A: SITE_A_DEVELIFIED, SITE_B: SITE_B_DEVELIFIED, SITE_C: SITE_C_DEVELIFIED,
                 SITE_D: SITE_D_DEVELIFIED, SITE_E: SITE_E_DEVELIFIED}
        return sites, bytes(CAVE_LEN), bytes(CAVE2_LEN)
    if version == 1:
        sites = {SITE_A: bl(SITE_A, A1), SITE_B: bl(SITE_B, B1), SITE_C: SITE_C_DEVELIFIED,
                 SITE_D: SITE_D_DEVELIFIED, SITE_E: SITE_E_DEVELIFIED}
        c1 = pack(cave_a1() + cave_b1())
        return sites, c1 + bytes(CAVE_LEN - len(c1)), bytes(CAVE2_LEN)
    sites = {SITE_A: bl(SITE_A, A2), SITE_B: bl(SITE_B, B2), SITE_C: b(SITE_C, C2),
             SITE_D: b(SITE_D, D2), SITE_E: bl(SITE_E, E2)}
    return sites, pack(cave_a2() + cave_b2()), pack(cave_c2() + cave_d2() + cave_e2())


def load(path):
    data = open(path, "rb").read()
    return bytearray(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def version_of(d):
    """0 develified, 1 or 2 patched, None unrecognised."""
    for v in (0, 1, 2):
        sites, c1, c2 = image(v)
        if (all(struct.unpack_from("<I", d, a)[0] == w for a, w in sites.items())
                and bytes(d[CAVE:CAVE + CAVE_LEN]) == c1 and bytes(d[CAVE2:CAVE2 + CAVE2_LEN]) == c2):
            return v
    return None


def write(d, version):
    sites, c1, c2 = image(version)
    for a, w in sites.items():
        struct.pack_into("<I", d, a, w)
    d[CAVE:CAVE + CAVE_LEN] = c1
    d[CAVE2:CAVE2 + CAVE2_LEN] = c2


def state(d):
    return {0: "develified (P2P selector joins with a leftover event: any track meets any track; "
               "lap slider greyed out)",
            1: "patched v1 (P2P selector joins with event -1000 - 1024 * track: same track only)",
            2: "patched v2 (P2P selector: lap slider on, joins with event -1000 - 4096 * track - 16 * laps: "
               "same track and laps only)"}.get(version_of(d))


def contents(d):
    """`patches` entry for rr3_build.py: '' develified, None unrecognised."""
    return {0: "", 1: "selector-p2p", 2: "selector-p2p@v2"}.get(version_of(d))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("lib")
    p = sub.add_parser("patch")
    p.add_argument("inp")
    p.add_argument("out")
    p.add_argument("--version", type=int, choices=(1, 2), default=VERSION,
                   help="1: track only; 2 (default): track and laps, lap slider on")
    p.add_argument("--restore", action="store_true", help="put the develified bytes back")
    a = ap.parse_args()

    d = load(a.lib if a.cmd == "check" else a.inp)
    if state(d) is None:
        sys.exit("unexpected bytes at the sites (0xf76210, 0xf766f8, 0x9f63c0, 0x9f64f4, 0x9f5678) or the caves "
                 "(0x1bb4c88, 0x1c117b0): not the v14.0.1 develified build?")
    if a.cmd == "check":
        print(state(d))
        return
    write(d, 0 if a.restore else a.version)
    out = gzip.compress(bytes(d)) if a.out.endswith(".gz") else bytes(d)
    open(a.out, "wb").write(out)
    print(f"{a.out}: {state(d)}")


if __name__ == "__main__":
    main()
