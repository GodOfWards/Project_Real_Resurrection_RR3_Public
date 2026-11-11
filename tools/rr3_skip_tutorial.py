#!/usr/bin/env python3
"""Skip the tutorials for a new player, in libRealRacing3.so (v14.0.1,
arm64, develified build). Issue #429, v1. Part of Project Real
Resurrection's work on Real Racing 3. Not affiliated with, endorsed or
supported by Electronic Arts.

At first start the splash step 0x13cead0 decides, for a new player
(tutorial state Character+4 == 0), between EA's own auto-skip 0xa69ff4 and
the Rookie Championship onboarding (0x13b5ec4). The choice reads a .bss
byte (0x1f9d6d5) that nothing writes, so the onboarding always runs.
0xa69ff4 marks the service/upgrade tips seen, gives the Nissan Silvia S15
(car 114) when the garage is empty, marks the tutorial entries done
(0x9a4d04), runs CareerHelper::CompleteTutorial (state 20) and saves; it
also calls a developer money grant (0xa675a8: 5,000,000 / 5,000 /
5,000,000 of three currencies). v1 takes the skip and drops the money:

  0x13ceb84  cbz w8, 0x13ceb9c  -> nop   (c8000034 -> d503201f)
  0xa6a124   bl  0xa675a8       -> nop   (97fff521 -> d503201f)

A player whose tutorial state is not 0 (existing save) never reaches the
patched branch. 0xa69ff4 has one caller (0x13ceb88); 0xa675a8 keeps its
debug menu caller (0xa672ac).

Research: analysis/tutorial.md. Guide: docs/skip-tutorial.md.

Usage:
  rr3_skip_tutorial.py check LIB
  rr3_skip_tutorial.py patch IN OUT [--restore]
IN may be gzipped; OUT is written uncompressed (or gzipped if it ends in .gz).
"""
import argparse
import gzip
import struct
import sys

VERSION = 1
NOP = 0xD503201F

# (site, develified word, patched word)
SITES = [
    (0x13CEB84, 0x340000C8, NOP),   # cbz w8, 0x13ceb9c (start the onboarding) -> nop: run the skip 0xa69ff4
    (0xA6A124, 0x97FFF521, NOP),    # bl 0xa675a8 (developer money)            -> nop
]


def load(path):
    data = open(path, "rb").read()
    return bytearray(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def state(d):
    """0 develified, 1 patched (v1), None unrecognised."""
    words = [struct.unpack_from("<I", d, s)[0] for s, _, _ in SITES]
    if words == [o for _, o, _ in SITES]:
        return 0
    if words == [n for _, _, n in SITES]:
        return 1
    return None


def contents(d):
    """`patches` entry for rr3_build.py: '' develified, None unrecognised.
    v1 is 'skip-tutorial' (only revisions carry @vN)."""
    s = state(d)
    return None if s is None else ("skip-tutorial" if s else "")


def describe(d):
    return {0: "develified", 1: f"patched v{VERSION}"}.get(state(d), "unrecognised")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("lib")
    p = sub.add_parser("patch")
    p.add_argument("inp")
    p.add_argument("out")
    p.add_argument("--restore", action="store_true", help="put the develified instructions back")
    a = ap.parse_args()

    d = load(a.lib if a.cmd == "check" else a.inp)
    if state(d) is None:
        sys.exit("skip-tutorial: unexpected bytes: not the v14.0.1 develified build?")
    if a.cmd == "check":
        print(f"skip-tutorial (new players skip the tutorials): {describe(d)}")
        return
    for site, develified, patched in SITES:
        struct.pack_into("<I", d, site, develified if a.restore else patched)
    out = gzip.compress(bytes(d)) if a.out.endswith(".gz") else bytes(d)
    open(a.out, "wb").write(out)
    print(f"{a.out}: skip-tutorial {describe(d)}")


if __name__ == "__main__":
    main()
