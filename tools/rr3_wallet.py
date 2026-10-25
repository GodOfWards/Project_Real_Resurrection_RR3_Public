#!/usr/bin/env python3
"""Read or set RR3 wallet balances in character.2.dat.

Wallet values are stored as 8-byte records (u64 LE XOR a per-field key).
Setting a balance also raises TotalPurchased by the same amount, like the
earlier third-party edit did, so Balance stays in line with the totals.

Usage:
  rr3_wallet.py show FILE
  rr3_wallet.py set IN OUT [--gold N] [--rd N] [--md N]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rr3_dat import load, xor, leb128  # noqa: E402
import struct

KEYS = {
    "m_Balance": bytes.fromhex("d46bca1c965efcc5"),
    "m_TotalPurchased": bytes.fromhex("d5b509a691596229"),
    "m_TotalAntiCheat": bytes.fromhex("334635a6e8d8309f"),
    "m_TotalEarnedToday": bytes.fromhex("006536282f591af3"),
}
CURRENCIES = {"gold": "m_Gold", "rd": "m_RDollars", "md": "m_MDollars"}


def name_ids(p):
    n = struct.unpack(">I", p[12:16])[0]
    o, ids = 0x14, {}
    for _ in range(n):
        e = o
        while p[e] not in (0, 1):
            e += 1
        name = p[o:e].decode("latin1")
        if p[e] == 0:
            ids[name], o = leb128(p, e + 1)
        else:
            c, o = leb128(p, e + 1)
            for _ in range(2 * c):
                _, o = leb128(p, o)
    return ids, o


def locate(p, cur, field):
    ids, data = name_ids(p)
    fid = ids[f"m_CurrencyWallet.{cur}.{field}[EHV].nValue"]
    pat = fid.to_bytes(2, "big") + b"\x00\x01\x05\x00\x00\x00\x08"
    i = p.find(pat, data)
    if i < 0 or p.find(pat, i + 1) >= 0:
        raise SystemExit(f"could not uniquely locate {cur}.{field}")
    return i + len(pat)


def get(p, cur, field):
    o = locate(p, cur, field)
    return int.from_bytes(bytes(a ^ b for a, b in zip(p[o:o + 8], KEYS[field])), "little")


def put(p, cur, field, value):
    o = locate(p, cur, field)
    p[o:o + 8] = bytes(a ^ b for a, b in zip(value.to_bytes(8, "little"), KEYS[field]))


def fix_checksum(p):
    """Last decrypted byte = XOR of every byte before it; the game rejects the save otherwise."""
    x = 0
    for b in p[:-1]:
        x ^= b
    return x


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["show", "set"])
    ap.add_argument("files", nargs="+")
    for c in CURRENCIES:
        ap.add_argument(f"--{c}", type=int)
    a = ap.parse_args()
    p = bytearray(load(a.files[0]))
    if a.cmd == "set":
        for c, cur in CURRENCIES.items():
            new = getattr(a, c)
            if new is None:
                continue
            old = get(p, cur, "m_Balance")
            put(p, cur, "m_Balance", new)
            if new > old:
                put(p, cur, "m_TotalPurchased", get(p, cur, "m_TotalPurchased") + new - old)
        p[-1] = fix_checksum(p)
        open(a.files[1], "wb").write(xor(bytes(p)))
    for c, cur in CURRENCIES.items():
        print(f"{c:5s} balance={get(p, cur, 'm_Balance'):>12,} purchased={get(p, cur, 'm_TotalPurchased'):>12,}")


if __name__ == "__main__":
    main()
