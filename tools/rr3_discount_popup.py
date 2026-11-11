#!/usr/bin/env python3
"""Stop the main menu crash at driver level 4 (the upgrade discount pop-up
reads a championship that isn't there), in libRealRacing3.so (v14.0.1,
arm64, develified build). Issue #234.

Every frame in the main menu, 0x1528f64 updates the upgrade discount
pop-up (data/upgrade_discount_popups.dat). Once the driver level reaches
the Seasons unlock level (0x9adc3c, level 4), it asks ChampionshipData
for the championship that holds the pop-up's stream (+0x44) and reads its
start time (+0x50) and duration (+0x58) to set the "offer expired" byte
+0xb. That data comes from EA's servers; without it the lookup 0x9a8cac
returns null and 0x1528ffc reads address 0x50 (SIGSEGV).

This patch adds the missing null check: no championship = offer expired
(+0xb = 1), the same path the game takes when an offer runs out. It needs
two free instruction slots, both in the same function:
- 0x1528fdc/0x1528fe4: `ldr x9, [x8, #0x98]` + `mov x0, x9` become one
  `ldr x0, [x8, #0x98]`; the freed slot sets w22 = 1 (callee-saved, so it
  survives the two calls; x22 is not used again before 0x1529094 writes it).
- 0x1529008: `mov w20, w20` is dropped (x20 was written by `mov w20, w0`,
  its top half is already zero); the slot holds `cbz x0`.

  0x1528fdc  ldr   x9, [x8, #0x98]    -> ldr  x0, [x8, #0x98]    (f9404d09 -> f9404d00)
  0x1528fe4  mov   x0, x9             -> mov  w22, #1            (aa0903e0 -> 52800036)
  0x1528ffc  ldr   x8, [x0, #0x50]    -> ldr  x10, [x19, #0x10]  (f9402808 -> f9400a6a)
  0x1529000  ldrsw x9, [x0, #0x58]    -> cbz  x0, 0x1529018      (b9805809 -> b40000c0)
  0x1529004  ldr   x10, [x19, #0x10]  -> ldr  x8, [x0, #0x50]    (f9400a6a -> f9402808)
  0x1529008  mov   w20, w20           -> ldrsw x9, [x0, #0x58]   (2a1403f4 -> b9805809)
  0x1529014  cset  w8, le             -> cset w22, le            (1a9fc7e8 -> 1a9fc7f6)
  0x1529018  strb  w8, [x19, #0xb]    -> strb w22, [x19, #0xb]   (39002e68 -> 39002e76)

0x152900c (add) and 0x1529010 (cmp) stay. With a championship the result
is the same as before.

Usage:
  rr3_discount_popup.py check LIB
  rr3_discount_popup.py patch IN OUT [--restore]
IN may be gzipped; OUT is written uncompressed (or gzipped if it ends in .gz).
"""
import argparse
import gzip
import struct
import sys

# (site, develified word, patched word)
SITES = [
    (0x1528FDC, 0xF9404D09, 0xF9404D00),    # ldr x9, [x8, #0x98]   -> ldr x0, [x8, #0x98]
    (0x1528FE4, 0xAA0903E0, 0x52800036),    # mov x0, x9            -> mov w22, #1
    (0x1528FFC, 0xF9402808, 0xF9400A6A),    # ldr x8, [x0, #0x50]   -> ldr x10, [x19, #0x10]
    (0x1529000, 0xB9805809, 0xB40000C0),    # ldrsw x9, [x0, #0x58] -> cbz x0, 0x1529018
    (0x1529004, 0xF9400A6A, 0xF9402808),    # ldr x10, [x19, #0x10] -> ldr x8, [x0, #0x50]
    (0x1529008, 0x2A1403F4, 0xB9805809),    # mov w20, w20          -> ldrsw x9, [x0, #0x58]
    (0x1529014, 0x1A9FC7E8, 0x1A9FC7F6),    # cset w8, le           -> cset w22, le
    (0x1529018, 0x39002E68, 0x39002E76),    # strb w8, [x19, #0xb]  -> strb w22, [x19, #0xb]
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
    return {"develified": "develified (crash at driver level 4 without championship data)",
            "patched": "patched (no championship = discount offer expired)"}.get(raw_state(d))


def contents(d):
    """`patches` entry for rr3_build.py: '' develified, None unrecognised."""
    return {"develified": "", "patched": "discount-popup"}.get(raw_state(d))


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
        sys.exit("unexpected bytes at 0x1528fdc..0x1529018: not the v14.0.1 develified build?")
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
