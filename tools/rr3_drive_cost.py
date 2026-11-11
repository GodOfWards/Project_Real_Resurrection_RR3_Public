#!/usr/bin/env python3
"""Remove the drive point ("energy") cost of Time Trials in libRealRacing3.so
(v14.0.1, arm64, develified build).

Drive points live in the profile at character+0x178 (m_driverPoints; spend
0xcaadf0, give 0xcaa950, balance 0xcaaf70). The cost of an event comes from
one function, 0xc68c88(event): 0 unless drive points are enabled and the event
is of the kind that uses them, otherwise a server-config value (default 1).
Everything else goes through it:

  - 0x152d908(character, car, event), "does this start need drive points?",
    returns false for a VIP car (0x9e7c88(4, car)), else cost > 0. The start
    paths at 0xf34740 and 0x149b6ec only check and spend when it is true.
  - 0xf43954 does the same with the VIP check inlined, then spends cost.
  - UI wrappers (0xc774f0, 0xc77540, 0xc775c4) return 0 for a VIP car and
    0xc68c88 otherwise.

The patch makes 0xc68c88 return 0 (`mov w0, wzr; ret`), so every event costs
nothing, as with a VIP car. The balance itself is left alone.

Usage:
  rr3_drive_cost.py check LIB
  rr3_drive_cost.py patch IN OUT [--restore]
IN may be gzipped; OUT is written uncompressed (or gzipped if it ends in .gz).
"""
import argparse
import gzip
import struct
import sys

SITE = 0xC68C88                    # .text VMA == file offset in this build
DEVELIFIED = (0xD10103FF, 0xA9017BFD)   # sub sp, sp, #0x40 ; stp x29, x30, [sp, #0x10]
PATCH = (0x2A1F03E0, 0xD65F03C0)   # mov w0, wzr ; ret


def load(path):
    data = open(path, "rb").read()
    return bytearray(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def state(d):
    w = struct.unpack_from("<2I", d, SITE)
    if w == DEVELIFIED:
        return "develified (Time Trials cost drive points unless the car is VIP)"
    if w == PATCH:
        return "patched (no drive point cost)"
    return None


def contents(d):
    """`patches` entry for rr3_build.py: '' develified, None unrecognised."""
    w = struct.unpack_from("<2I", d, SITE)
    return "free-drives" if w == PATCH else "" if w == DEVELIFIED else None


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
    s = state(d)
    if s is None:
        sys.exit(f"unexpected bytes at {SITE:#x}: not the v14.0.1 develified build?")
    if a.cmd == "check":
        print(s)
        return
    struct.pack_into("<2I", d, SITE, *(DEVELIFIED if a.restore else PATCH))
    out = gzip.compress(bytes(d)) if a.out.endswith(".gz") else bytes(d)
    open(a.out, "wb").write(out)
    print(f"{a.out}: {state(d)}")


if __name__ == "__main__":
    main()
