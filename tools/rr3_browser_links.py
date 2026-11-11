#!/usr/bin/env python3
"""rr3:// links in the game's own browser go to the game, in
libRealRacing3.so (v14.0.1, arm64, develified build). Issue #492 (#427).

Part of Project Real Resurrection's work on Real Racing 3. Not affiliated
with, endorsed or supported by Electronic Arts.

The game's browser (CloudCell UserInterfaceManager WebView) asks
LoadShouldStartCallback (0x1cbbaa0) about every link: after an optional
hook (this+0x60), close:// closes it, externalbrowser://X opens http://X in
the phone's browser, anything else loads in the WebView, which knows only
http(s). So the PRR site's OMP invite Join (rr3://MultiplayerInvite/...)
could not reach the game from there; it went through Chrome
(analysis/online-multiplayer.md, "Joining from the game's own browser").

v1 (`browser-rr3@v1`): right after the hook check, a link starting with
rr3:// is handed to the game exactly as the debug menu's "Main Menu >
Enter Deep Link" does (0xa7c82c..0xa7c85c):

    0xcd8768(url, &cmd, &params)          parse rr3://<cmd>/<params>
    0x14c7a7c(0x10ab9c4(), &cmd, &params, 0)
                                          main-menu dispatcher: the lookup
                                          (0xa3b74c) upper-cases cmd;
                                          MULTIPLAYERINVITE (13) opens the
                                          invite popup 0xf790ac

then the browser closes as for close:// (vtable +0x50) and the callback
returns false (not loaded). Other links are unchanged.

  0x1cbbae8  adrp x8, 0x1fc6000   -> b 0x158456c

Cave 0x158456c (47 words, tools/asm/rr3_browser_links.s), the free end of
the dead physics-state compare 0x1583704..0x15846a8
(tables/lib-code-caves.csv, requires nothing).

Usage:
  rr3_browser_links.py check LIB
  rr3_browser_links.py patch IN OUT [--restore]
IN may be gzipped; OUT is written uncompressed (or gzipped if it ends in .gz).
"""
import argparse
import gzip
import struct
import sys

VERSION = 1
REQUIRES = []                         # the cave needs nothing switched off first

SITE, SITE_DEVELIFIED = 0x1CBBAE8, 0xF0001848     # adrp x8, 0x1fc6000
CAVE = 0x158456C
CAVE_END = 0x15846A8                  # end of the dead function (cave table)

# tools/asm/rr3_browser_links.s linked at 0x158456c (build line in that file).
CAVE_V1 = (
    0x39400268, 0xF9400669, 0xF9400A6A, 0xD341FD0B, 0x9100066C, 0x7200011F, 0x9A890169,
    0x9A8A018A, 0xF100193F, 0x54000483, 0xB940014B, 0x528E4E4C, 0x72A7466C, 0x6B0C017F,
    0x540003E1, 0x7940094B, 0x5285E5EC, 0x6B0C017F, 0x54000361, 0xA9007FFF, 0xF9000BFF,
    0xA901FFFF, 0xF90017FF, 0xAA1303E0, 0x910003E1, 0x910063E2, 0x97DD5065, 0x97EC9CFB,
    0x910003E1, 0x910063E2, 0x2A1F03E3, 0x97FD0D25, 0x394003E8, 0x36000068, 0xF9400BE0,
    0x94224D56, 0x394063E8, 0x36000068, 0xF94017E0, 0x94224D52, 0xF9400288, 0xAA1403E0,
    0xF9402908, 0xD63F0100, 0x141CDE11, 0xD0005208, 0x141CDD32)
# The develified words of that slice (the dead function).
CAVE_DEVELIFIED = (
    0x6B09011F, 0x54FFBA00, 0x90FF7600, 0x91226000, 0x97EC6D27, 0x2A1F03F5, 0xB94ED688,
    0xB94ED669, 0x6B09011F, 0x54FFB980, 0xF0FF7520, 0x910C4000, 0x97EC6D1F, 0x2A1F03F5,
    0xB94EDA88, 0xB94EDA69, 0x6B09011F, 0x54FFB900, 0xD0FF7460, 0x9109E400, 0x97EC6D17,
    0x2A1F03F5, 0xB94EF288, 0xB94EF269, 0x6B09011F, 0x54FFB880, 0xB0FF7640, 0x91041000,
    0x97EC6D0F, 0x2A1F03F5, 0xB94EF688, 0xB94EF669, 0x6B09011F, 0x54FFB800, 0xB0FF73E0,
    0x912EC000, 0x97EC6D07, 0x2A1F03F5, 0xB94EFA88, 0xB94EFA69, 0x6B09011F, 0x54FFB780,
    0xF0FF7800, 0x91271000, 0x97EC6CFF, 0x2A1F03F5, 0xBD4EFE80)
assert len(CAVE_V1) == len(CAVE_DEVELIFIED) == 47 and CAVE + 4 * 47 <= CAVE_END


def b(at, to):
    return 0x14000000 | (((to - at) >> 2) & 0x3FFFFFF)


def image(version):
    """[(address, word)] for develified (0) or a version."""
    if version == 0:
        return [(SITE, SITE_DEVELIFIED)] + [(CAVE + 4 * i, w) for i, w in enumerate(CAVE_DEVELIFIED)]
    return [(SITE, b(SITE, CAVE))] + [(CAVE + 4 * i, w) for i, w in enumerate(CAVE_V1)]


def load(path):
    data = open(path, "rb").read()
    return bytearray(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def version_of(d):
    """0 develified, 1 patched, None unrecognised."""
    for v in (0, 1):
        if all(struct.unpack_from("<I", d, a)[0] == w for a, w in image(v)):
            return v
    return None


def write(d, version):
    for a, w in image(version):
        struct.pack_into("<I", d, a, w)


def state(d):
    return {0: "develified (rr3:// links in the game's browser fail: ERR_UNKNOWN_URL_SCHEME)",
            1: "patched v1 (rr3:// links in the game's browser go to the game's deep-link dispatcher; "
               "the browser closes)"}.get(version_of(d))


def contents(d):
    """`patches` entry for rr3_build.py: '' develified, None unrecognised."""
    return {0: "", 1: "browser-rr3@v1"}.get(version_of(d))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("lib")
    p = sub.add_parser("patch")
    p.add_argument("inp")
    p.add_argument("out")
    p.add_argument("--restore", action="store_true", help="put the develified bytes back")
    a = ap.parse_args()

    d = load(a.lib if a.cmd == "check" else a.inp)
    if state(d) is None:
        sys.exit("unexpected bytes at the site (0x1cbbae8) or the cave (0x158456c): "
                 "not the v14.0.1 develified build?")
    if a.cmd == "check":
        print(state(d))
        return
    write(d, 0 if a.restore else VERSION)
    out = gzip.compress(bytes(d)) if a.out.endswith(".gz") else bytes(d)
    open(a.out, "wb").write(out)
    print(f"{a.out}: {state(d)}")


if __name__ == "__main__":
    main()
