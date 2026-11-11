#!/usr/bin/env python3
"""Decrypt / re-encrypt RR3 character.*.dat saves and summarize differences.

The file is XORed with a fixed 64-byte key (same key for both samples seen so far).
XOR is symmetric, so `decrypt` also re-encrypts.

Usage:
  rr3_dat.py decrypt IN OUT
  rr3_dat.py header FILE            (FILE may be encrypted or decrypted)
  rr3_dat.py tables A B             (compare IDX:/[id] table entry counts)
"""
import re
import struct
import sys

KEY = bytes.fromhex(
    "6495e450cfd20c325482fc438013a15e0b465cd7c687a8a955a794101133e767"
    "b0c9efda21113d918d884cc9fa815d9f171cda974b9cac92607fff3c40c65000"
)
MAGIC = bytes.fromhex("abcffcba")


def xor(data):
    return bytes(b ^ KEY[i % len(KEY)] for i, b in enumerate(data))


def load(path):
    data = open(path, "rb").read()
    return data if data[:4] == MAGIC else xor(data)


def leb128(p, o):
    v = s = 0
    while True:
        b = p[o]
        o += 1
        v |= (b & 0x7F) << s
        s += 7
        if b < 0x80:
            return v, o


def header(p):
    magic, version, size, names, unk = struct.unpack(">IIIII", p[:20])
    return {"magic": hex(magic), "version": version, "file_size": size,
            "name_count?": names, "unknown_0x10": hex(unk)}


def tables(p):
    out = {}
    for m in re.finditer(rb"([A-Za-z0-9_:\[\]\.\*]+)\x01", p[:0x60000]):
        name = m.group(1).decode()
        if name.startswith("IDX") or name.endswith(":[id]"):
            out[name] = leb128(p, m.end())[0]
    return out


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "decrypt":
        open(argv[3], "wb").write(xor(open(argv[2], "rb").read()))
    elif cmd == "header":
        print(header(load(argv[2])))
    elif cmd == "tables":
        a, b = tables(load(argv[2])), tables(load(argv[3]))
        for k in sorted(set(a) | set(b)):
            if a.get(k) != b.get(k):
                print(f"{k:55s} {a.get(k)!s:>6} {b.get(k)!s:>6}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)
