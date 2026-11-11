#!/usr/bin/env python3
"""Decrypt RR3 .nct game data files (e.g. data/events.dat.nct).

.nct files are RC4 with two twists, taken from the loader at 0x12bc330 in
libRealRacing3.so (v14.0.1): the S-box starts from a fixed permutation
(16 rodata blocks) instead of 0..255, and after the key schedule the first
133 PRGA steps are run without output. Key: 8 bytes at 0x49c8f8.
RC4 is symmetric, so the same command also re-encrypts.

Usage:
  rr3_nct.py IN OUT [--lib game/develified-libRealRacing3.so.gz]
"""
import argparse
import gzip
import os

SBOX_BLOCKS = [0x38b600, 0x38bcb0, 0x3884d0, 0x38b610, 0x38be50, 0x38bad0, 0x389a70, 0x3882d0,
               0x38aab0, 0x38a860, 0x38a3a0, 0x38a870, 0x389a80, 0x389a90, 0x388060, 0x388810]
KEY_ADDR = 0x49c8f8  # .rodata: file offset == address


def keystream_state(lib):
    s = bytearray(b"".join(lib[a:a + 16] for a in SBOX_BLOCKS))
    key = lib[KEY_ADDR:KEY_ADDR + 8]
    j = 0
    for i in range(256):
        j = (j + s[i] + key[i & 7]) & 255
        s[i], s[j] = s[j], s[i]
    j = 0
    for i in range(1, 134):
        j = (j + s[i]) & 255
        s[i], s[j] = s[j], s[i]
    return s, 133, j


def crypt(data, lib):
    s, i, j = keystream_state(lib)
    out = bytearray(len(data))
    for n, c in enumerate(data):
        i = (i + 1) & 255
        j = (j + s[i]) & 255
        s[i], s[j] = s[j], s[i]
        out[n] = c ^ s[(s[i] + s[j]) & 255]
    return bytes(out)


def read_lib(path):
    return (gzip.open if path.endswith(".gz") else open)(path, "rb").read()


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--lib", default=os.path.join(here, "..", "game", "develified-libRealRacing3.so.gz"))
    a = ap.parse_args()
    out = crypt(open(a.src, "rb").read(), read_lib(a.lib))
    open(a.dst, "wb").write(out)
    print(f"wrote {len(out)} bytes, magic {out[:4]!r}")


if __name__ == "__main__":
    main()
