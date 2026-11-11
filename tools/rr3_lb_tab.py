#!/usr/bin/env python3
"""Event leaderboards open on the Global tab instead of Friends, in
libRealRacing3.so (v14.0.1, arm64, develified build). Issue #609; research
in analysis/leaderboard-tabs.md. Guide: docs/leaderboard-tab.md.

Version 1 (`lb-global`, only revisions carry @vN).

The leaderboard set-up 0xda2780 takes a requested tab in w6 (0 Global,
1 Friends, 2 Group). For Friends it keeps Friends only when the friends list
(RacerManager FriendDetails, getter 0x135623c, filled by 10472) is not
empty; otherwise it falls back to Global. Only
FrontEnd2::EventLeaderboardWithGroups asks for Friends: its constructor
stores 1 at +0x3e0 (0xda98a4) and its show function passes it:

  0xda9700  ldr w6, [x19, #0x3e0]   ; requested tab (always 1)
  ...
  0xda9718  bl  0xda2780

The patch makes that `mov w6, wzr`: the leaderboard opens on Global. The
field +0x3e0, the logged-in state, the friends list and the tab buttons are
not touched, so tapping Friends or Group works as before. The five
instructions up to the call set only x1..x5, so w6 reaches 0xda2780 as 0.

Screens: the event screen leaderboard (Time Trial, WTT/TTC, LTS; built at
0xdc19e0), the Hyundai event screen (0xdf3dcc) and the post-race leaderboard
(0xf34318). OMP and Race Teams already ask for Global (w6 = 0).

Usage:
  rr3_lb_tab.py check LIB
  rr3_lb_tab.py patch IN OUT [--restore]
IN may be gzipped; OUT is written uncompressed (or gzipped if it ends in .gz).
"""
import argparse
import gzip
import struct
import sys

VERSION = 1
SITE = 0xDA9700                    # .text VMA == file offset in this build
DEVELIFIED = 0xB943E266            # ldr w6, [x19, #0x3e0]
PATCH = 0x2A1F03E6                 # mov w6, wzr  (orr w6, wzr, wzr)
REQUIRES = []


def load(path):
    data = open(path, "rb").read()
    return bytearray(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def word(d):
    return struct.unpack_from("<I", d, SITE)[0]


def state(d):
    w = word(d)
    if w == DEVELIFIED:
        return "develified (event leaderboards ask for the Friends tab)"
    if w == PATCH:
        return f"patched v{VERSION} (event leaderboards open on Global)"
    return None


def contents(d):
    """`patches` entry for rr3_build.py: '' develified, None unrecognised."""
    w = word(d)
    return "lb-global" if w == PATCH else "" if w == DEVELIFIED else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("lib")
    p = sub.add_parser("patch")
    p.add_argument("inp")
    p.add_argument("out")
    p.add_argument("--restore", action="store_true", help="put the develified instruction back")
    a = ap.parse_args()

    d = load(a.lib if a.cmd == "check" else a.inp)
    s = state(d)
    if s is None:
        sys.exit(f"unexpected bytes at {SITE:#x}: not the v14.0.1 develified build?")
    if a.cmd == "check":
        print(s)
        return
    struct.pack_into("<I", d, SITE, DEVELIFIED if a.restore else PATCH)
    out = gzip.compress(bytes(d)) if a.out.endswith(".gz") else bytes(d)
    open(a.out, "wb").write(out)
    print(f"{a.out}: {state(d)}")


if __name__ == "__main__":
    main()
