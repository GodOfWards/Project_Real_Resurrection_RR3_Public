#!/usr/bin/env python3
"""Put our build tag in libRealRacing3.so (v14.0.1, arm64, develified build),
so the game shows it next to 14.0.1 and sends it to the Cloudcell server
(issue #202). Guide: docs/build-tag.md.

Settings shows "Real Racing 3 14.0.1 [a527]". The part in brackets is the
game's build number: the text of the file hbn (files/apk/res/hbn, "a527"),
read by GetBuildNoFromFile, 0x12c2008, into a zeroed 128-byte buffer
(x1). It has two callers:
  0x12c1be0  the version line builder 0x12c1af8 (via 0x12c1b9c): Settings,
             the OMP master server request and other logs;
  0x12c1e6c  the line of subsync 68, "RealRacing3/14.0.1 [a527]", sent to
             the Cloudcell server with almost every sync.
The game rewrites hbn from its packed data at every start, so the file
cannot be changed (tested 2026-10-27).

This patch replaces the start of 0x12c2008 with a copy of our tag:

  0x12c2008  mov x0, x1           aa0103e0   destination: the caller's buffer
  0x12c200c  adr x1, 0x12c2018    10000061   source: the tag below
  0x12c2010  mov x2, #0x80        d2801002   128 bytes, the whole buffer
  0x12c2014  b   0x1e17c00        (memcpy)   tail call, returns to the caller
  0x12c2018  the tag, padded with NUL bytes to 128 (at most 127 characters)

The rest of the function (to 0x12c211c) is no longer reached. hbn is not
read any more, and the date fallback in 0x12c1b9c is skipped because the
tag is never empty. Both callers then show "[TAG]": Settings shows
"Real Racing 3 14.0.1 [PRR b43-alpha]".

The tag (decided in #202, Tom 2026-10-27): "PRR bNN-CHANNEL", where bNN is
the build's own number in tables/builds.csv and CHANNEL is
  alpha   dev team only (quick test builds, not on GitHub);
  beta    open testing (GitHub prerelease);
  stable  public release, confirmed in game, no open bug issue against it.
Changing the channel changes the lib, so it is a new build with its own
number (b43-alpha, then b44-beta for the same code).

Usage:
  rr3_build_tag.py check LIB
  rr3_build_tag.py patch IN OUT --channel {alpha,beta,stable} [--build bNN]
  rr3_build_tag.py patch IN OUT --tag TEXT      any tag, for testing
  rr3_build_tag.py patch IN OUT --restore
--build defaults to the next free number in tables/builds.csv (the number
`rr3_build.py add` will give the lib). A tagged lib can be re-tagged
directly. IN may be gzipped; OUT is written uncompressed (or gzipped if it
ends in .gz).
"""
import argparse
import csv
import gzip
import os
import re
import struct
import sys

SITE = 0x12C2008               # GetBuildNoFromFile
TAG_AT = SITE + 0x10
TAG_LEN = 0x80                 # the callers' buffer
END = TAG_AT + TAG_LEN         # 0x12c2098
MEMCPY = 0x1E17C00             # PLT stub, R_AARCH64_JUMP_SLOT memcpy
DEVELIFIED = bytes.fromhex(
    "ff8301d1fd7b03a9f52300f9f44f05a9fdc3009155d03bd5a81640f9f30301aa"
    "a8831ff8486700d008a10b9108fddf0848040036486700d008814b39c8020034"
    "a086fff000840a91e803009121008052288aff97e80b40b9e10340f909108052"
    "e00313aa1f0102711431891ae20314aae2562d94e00300917f6a3438928aff97"
    "9f0200718c000054a08eff9000483c91")
STUB = struct.pack("<4I",
                   0xAA0103E0,                                          # mov x0, x1
                   0x10000001 | (((TAG_AT - (SITE + 4)) >> 2) << 5),    # adr x1, TAG_AT
                   0xD2800002 | (TAG_LEN << 5),                         # mov x2, #0x80
                   0x14000000 | (((MEMCPY - (SITE + 12)) >> 2) & 0x3FFFFFF))  # b memcpy
CHANNELS = ("alpha", "beta", "stable", "support")
TAG_OK = re.compile(r"[ -:<-~]{1,%d}" % (TAG_LEN - 1))     # printable ASCII but ';' (patches column)
BUILDS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tables", "builds.csv")


def load(path):
    data = open(path, "rb").read()
    return bytearray(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def tag(d):
    """'' develified, the tag if patched, None unrecognised."""
    b = bytes(d[SITE:END])
    if b == DEVELIFIED:
        return ""
    if b[:16] != STUB:
        return None
    t = b[16:].split(b"\0")[0]
    if b[16 + len(t):] != b"\0" * (TAG_LEN - len(t)) or not TAG_OK.fullmatch(t.decode("latin-1")):
        return None
    return t.decode()


def contents(d):
    """`patches` entry for rr3_build.py: '' develified, None unrecognised.
    e.g. build-tag=PRR b43-alpha."""
    t = tag(d)
    return None if t is None else (f"build-tag={t}" if t else "")


def next_build():
    nums = [int(r["build"][1:]) for r in csv.DictReader(open(BUILDS, newline=""))
            if re.fullmatch(r"b\d+", r["build"])]
    return f"b{max(nums) + 1:02d}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("lib")
    p = sub.add_parser("patch")
    p.add_argument("inp")
    p.add_argument("out")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--channel", choices=CHANNELS, help="tag PRR bNN-CHANNEL")
    g.add_argument("--tag", help=f"any tag, 1-{TAG_LEN - 1} printable characters, no ';' (testing)")
    g.add_argument("--restore", action="store_true", help="put the develified function back")
    p.add_argument("--build", help="build number for --channel (default: next free in tables/builds.csv)")
    a = ap.parse_args()

    d = load(a.lib if a.cmd == "check" else a.inp)
    t = tag(d)
    if t is None:
        sys.exit("unexpected bytes at 0x12c2008: not the v14.0.1 develified build?")
    if a.cmd == "check":
        print(f"patched (build tag [{t}])" if t else "develified (build number read from hbn)")
        return

    if a.restore:
        d[SITE:END] = DEVELIFIED
    else:
        if a.channel:
            build = a.build or next_build()
            if not re.fullmatch(r"b\d{2,}", build):
                sys.exit(f"--build must look like b43, got {build!r}")
            new = f"PRR {build}-{a.channel}"
        else:
            if a.build:
                sys.exit("--build goes with --channel")
            new = a.tag
        if not TAG_OK.fullmatch(new):
            sys.exit(f"tag must be 1-{TAG_LEN - 1} printable ASCII characters without ';', got {new!r}")
        d[SITE:END] = STUB + new.encode().ljust(TAG_LEN, b"\0")
    out = gzip.compress(bytes(d)) if a.out.endswith(".gz") else bytes(d)
    open(a.out, "wb").write(out)
    print(f"{a.out}: " + (f"build tag [{tag(d)}]" if tag(d) else "develified"))


if __name__ == "__main__":
    main()
