#!/usr/bin/env python3
"""Race Selector: raise the lap slider and the race lap clamp to 99 laps,
in libRealRacing3.so (v14.0.1, arm64, develified build). Issue #116.

Two limits stand between the Race Selector and a long race
(analysis/lap-limit.md):
- the selector's lap slider (widget 20040) is set to 1..10 by
  `SetRange(slider, 1, 10)` (0x107e538) during screen setup;
- SetRaceLapCount (0x10b2d18) clamps every race (selector and events) to
  1..20 and logs a warning above 20. Its result goes to game+0x10c80.

This patch raises both to 99. Four immediates, no code cave, no new
instruction shapes:

  0xd98974   mov w2, #0xa    -> mov w2, #0x63   (52800142 -> 52800c62)  slider max
  0x10b2d2c  cmp w3, #0x15   -> cmp w3, #0x64   (7100547f -> 7101907f)  clamp test
  0x10b2d4c  mov w4, #0x14   -> mov w4, #0x63   (52800284 -> 52800c64)  log argument only
  0x10b2d54  mov w3, #0x14   -> mov w3, #0x63   (52800283 -> 52800c63)  clamped value

Below 21 laps nothing changes. Event data above 20 laps (none in EA's own
data) is no longer clamped to 20 but to 99.

Usage:
  rr3_race_laps.py check LIB
  rr3_race_laps.py patch IN OUT [--restore]
IN may be gzipped; OUT is written uncompressed (or gzipped if it ends in .gz).
"""
import argparse
import gzip
import struct
import sys

LAPS = 99

# (site, develified word, patched word)
SITES = [
    (0xD98974, 0x52800142, 0x52800C62),     # mov w2, #0xa  -> mov w2, #0x63  (slider max)
    (0x10B2D2C, 0x7100547F, 0x7101907F),    # cmp w3, #0x15 -> cmp w3, #0x64  (clamp test)
    (0x10B2D4C, 0x52800284, 0x52800C64),    # mov w4, #0x14 -> mov w4, #0x63  (log argument)
    (0x10B2D54, 0x52800283, 0x52800C63),    # mov w3, #0x14 -> mov w3, #0x63  (clamped value)
]


def load(path):
    data = open(path, "rb").read()
    return bytearray(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def raw_state(d):
    """'develified', 'patched' or None (unrecognised)."""
    words = [struct.unpack_from("<I", d, site)[0] for site, _, _ in SITES]
    if words == [s for _, s, _ in SITES]:
        return "develified"
    if words == [p for _, _, p in SITES]:
        return "patched"
    return None


def state(d):
    return {"develified": "develified (selector slider 1..10, races clamped to 20 laps)",
            "patched": f"patched (selector slider 1..{LAPS}, races clamped to {LAPS} laps)"}.get(raw_state(d))


def contents(d):
    """`patches` entry for rr3_build.py: '' develified, None unrecognised."""
    return {"develified": "", "patched": "race-laps"}.get(raw_state(d))


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
        sys.exit("unexpected bytes at 0xd98974 / 0x10b2d2c..0x10b2d54: not the v14.0.1 develified build?")
    if a.cmd == "check":
        print(state(d))
        return
    for site, develified, patched in SITES:
        struct.pack_into("<I", d, site, develified if a.restore else patched)
    out = gzip.compress(bytes(d)) if a.out.endswith(".gz") else bytes(d)
    open(a.out, "wb").write(out)
    print(f"{a.out}: {state(d)}")


if __name__ == "__main__":
    main()
