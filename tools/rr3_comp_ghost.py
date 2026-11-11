#!/usr/bin/env python3
"""Upload the Time Trial ghost of competition events (WTT, TTC) right after
the run, like a normal Time Trial, in libRealRacing3.so (v14.0.1, arm64,
develified build). Issue #392; research in analysis/leaderboard-ghosts.md 3.3.
Guide: docs/competition-ghosts.md.

At the Time Trial finish (0x10458c8..0x10459c8) the game computes
w23 = 0xc4080c([[event+0x130]+0x108]+0x10), true for a competition stream
(sub type 2: WTT, TTC), and branches:

  0x10459bc  tbz w23, #0, 0x10459c8   ; normal Time Trial -> 0x10459c8
  0x10459c0  bl  0xf4e898             ; competition: hold one ghost (GOT 0x1f736b0)
  0x10459c4  b   0x10459cc
  0x10459c8  bl  0xf4e708             ; queue the ghost (GOT 0x1f736a8), save ughd.bin

0x1045a40 then calls 0xf4ee58, which sends one 10695 (-> PUT -> 10694) per
queued ghost. The held ghost is sent only by 0xf4ea14, from the 10451 reply
handler of CompetitionUploadResultTask, and that task is created only for a
registered competition (LTS record +0x10 != -1). Every WTT record has -1, so
a WTT ghost is held, never sent, and freed at the next Time Trial set-up.

The patch makes the branch unconditional: `b 0x10459c8`. Every Time Trial
finish queues its ghost and uploads it at once.

  - Both targets take the same arguments (w0 event, x1/w2 ghost data,
    x3 name, w4..w6, s0..s3: set at 0x1045990..0x10459b8) and build the same
    0x50-byte record, so the queued item is what a normal Time Trial queues.
  - w23 is not read after the branch.
  - 0xf4e898 is then never called (its only caller is 0x10459c0), so the
    held slot stays empty. Its readers check for that: 0xf4ea14 (cbz at
    0xf4ea40) and 0xf4e9c0 (cbz at 0xf4e9d8). Nothing frees it twice.
  - The result upload (10451, UploadResultTask) is in another function and
    does not read this branch.

Usage:
  rr3_comp_ghost.py check LIB
  rr3_comp_ghost.py patch IN OUT [--restore]
IN may be gzipped; OUT is written uncompressed (or gzipped if it ends in .gz).
"""
import argparse
import gzip
import struct
import sys

SITE = 0x10459BC                   # .text VMA == file offset in this build
TARGET = 0x10459C8                 # bl 0xf4e708 (queue the ghost)
DEVELIFIED = 0x36000077            # tbz w23, #0, 0x10459c8
PATCH = 0x14000000 | ((TARGET - SITE) >> 2)   # b 0x10459c8
REQUIRES = []


def load(path):
    data = open(path, "rb").read()
    return bytearray(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def word(d):
    return struct.unpack_from("<I", d, SITE)[0]


def state(d):
    w = word(d)
    if w == DEVELIFIED:
        return "develified (a WTT/TTC finish holds its ghost; it is never uploaded)"
    if w == PATCH:
        return "patched (every Time Trial finish uploads its ghost, WTT and TTC included)"
    return None


def contents(d):
    """`patches` entry for rr3_build.py: '' develified, None unrecognised."""
    w = word(d)
    return "comp-ghost" if w == PATCH else "" if w == DEVELIFIED else None


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
