#!/usr/bin/env python3
"""Livery editor: raise the vinyl (decal layer) limit per car from 50,
in libRealRacing3.so (v14.0.1, arm64, develified build). Issue #601.

The limit is one read-only int32 in .rodata, 0x4c66a0 = 50 (file offset =
address). Code reads it only through GOT slot 0x1f71668 (one
R_AARCH64_RELATIVE), at nine places:
- 0xd847fc, 0xd8634c, 0xd86cd4: the three "add vinyl" paths of
  CustomiseDecalsScreen, `count >= limit` -> "LAYERS LIMIT REACHED";
- 0xd83d58: the "count / limit" counter text;
- 0xd82570: the layer bar, which makes `limit` slot widgets when the editor
  opens (a vector, not a fixed array);
- 0xe3c808, 0xe3d03c, 0xe3d1d8, 0xe3d39c: debug menu entries
  (Customisation|Add Decals Current Car, Opponents Max Decals).
The save keeps the vinyls as a list of any length (no clamp on load), and
the race uses one baked texture, so nothing else is sized by the limit
(analysis/vinyl-limit.md).

This patch writes a new value there (default 300, `--limit N`, 51..1000;
Tom, 2026-11-10):

  0x4c66a0  .word 50  ->  .word 300   (32000000 -> 2c010000)

The decal texture cache (50 images, 0xc83090) is not changed: more than
50 different images on one car only make a re-bake slower.

Usage:
  rr3_vinyl_limit.py check LIB
  rr3_vinyl_limit.py patch IN OUT [--limit N] [--restore]
IN may be gzipped; OUT is written uncompressed (or gzipped if it ends in .gz).
"""
import argparse
import gzip
import struct
import sys

SITE = 0x4C66A0         # .rodata int32, the vinyl limit
GOT = 0x1F71668         # its GOT slot (filled at load from .rela.dyn)
DEVELIFIED = 50
DEFAULT = 300
LOW, HIGH = DEVELIFIED + 1, 1000
# Bytes around the value, to make sure this is the develified layout.
BEFORE = bytes.fromhex("45694533245f3000")   # tail of a mangled name ("EiE3$_0\0")


def load(path):
    data = open(path, "rb").read()
    return bytearray(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def limit(d):
    """The vinyl limit in the lib, or None (unrecognised)."""
    if len(d) < SITE + 4 or d[SITE - len(BEFORE):SITE] != BEFORE:
        return None
    n = struct.unpack_from("<i", d, SITE)[0]
    return n if n == DEVELIFIED or LOW <= n <= HIGH else None


def state(d):
    n = limit(d)
    if n is None:
        return None
    if n == DEVELIFIED:
        return "develified (50 vinyls per car)"
    return f"patched ({n} vinyls per car)"


def contents(d):
    """`patches` entry for rr3_build.py: '' develified, None unrecognised.
    e.g. vinyl-limit=300."""
    n = limit(d)
    return None if n is None else ("" if n == DEVELIFIED else f"vinyl-limit={n}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("lib")
    p = sub.add_parser("patch")
    p.add_argument("inp")
    p.add_argument("out")
    p.add_argument("--limit", type=int, default=DEFAULT, help=f"vinyls per car, {LOW}..{HIGH} (default {DEFAULT})")
    p.add_argument("--restore", action="store_true", help="put the develified value (50) back")
    a = ap.parse_args()

    d = load(a.lib if a.cmd == "check" else a.inp)
    if state(d) is None:
        sys.exit(f"unexpected bytes at {SITE:#x}: not the v14.0.1 develified build?")
    if a.cmd == "check":
        print(state(d))
        return
    if not a.restore and not LOW <= a.limit <= HIGH:
        sys.exit(f"--limit must be {LOW}..{HIGH}")
    struct.pack_into("<i", d, SITE, DEVELIFIED if a.restore else a.limit)
    out = gzip.compress(bytes(d)) if a.out.endswith(".gz") else bytes(d)
    open(a.out, "wb").write(out)
    print(f"{a.out}: {state(d)}")


if __name__ == "__main__":
    main()
