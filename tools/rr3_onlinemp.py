#!/usr/bin/env python3
"""List or add OMP car groups in data/onlinemp.dat(.nct) (issue #383).

Part of Project Real Resurrection's work on Real Racing 3. Not affiliated
with, endorsed or supported by Electronic Arts.

onlinemp.dat (analysis/online-multiplayer.md "Q7 (part)") is RRCE v5: u32
group count, then per group a string key (u32 length + bytes), u32 n and n
u32 car ids; then the settings block. The schedule reply (10536 field 4)
names one group by key, and the phone checks that every car of it
resolves. This tool adds our own groups (keys starting with PRR_) and
keeps EA's groups and the settings block byte for byte, so a phone that
gets the file by asset update (rr3_cc_server.py --asset-update) can race
them with no lib change.

  list IN                       the groups with car names
  add IN OUT --group KEY --cars ID,ID,...
                                add (or replace) one of our groups
  apply IN OUT [--groups FILE]  set our groups to FILE's (default
                                tools/rr3-omp-groups.json): ours not in it
                                are removed, EA's are untouched
  remove IN OUT --group KEY     remove one of our groups

IN/OUT are encrypted .nct files as on the phone, or decrypted (RRCE) files;
OUT is written the way IN was. Car ids must be in tables/car-index.csv;
2-20 cars per group. Only PRR_ keys can be added, replaced or removed.

v1 (2026-11-06): list, add, apply, remove. Untested in game: whether the
game loads an onlinemp.dat that comes by asset update, and whether a PRR_
key works where EA's use OMP_V..._TOURNAMENT_... (#383 "Test").
"""
import argparse
import csv
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rr3_nct  # noqa: E402

VERSION = "1"
MAGIC = b"RRCE"
FORMAT = 5
OURS = "PRR_"
CARS_MIN, CARS_MAX = 2, 20
LIB = os.path.join(HERE, "..", "game", "develified-libRealRacing3.so.gz")
CAR_INDEX = os.path.join(HERE, "..", "tables", "car-index.csv")
GROUPS_FILE = os.path.join(HERE, "rr3-omp-groups.json")


def load(path, lib=LIB):
    """(decrypted bytes, was encrypted)."""
    raw = open(path, "rb").read()
    if raw[:4] == MAGIC:
        return raw, False
    d = rr3_nct.crypt(raw, rr3_nct.read_lib(lib))
    if d[:4] != MAGIC:
        raise ValueError(f"{path}: not onlinemp.dat (no RRCE, encrypted or not)")
    return d, True


def save(path, d, encrypted, lib=LIB):
    open(path, "wb").write(rr3_nct.crypt(d, rr3_nct.read_lib(lib)) if encrypted else d)


def parse(d):
    """(version, [(key, [car ids])], settings block bytes)."""
    if d[:4] != MAGIC:
        raise ValueError("not RRCE")
    version, n = struct.unpack_from("<II", d, 4)
    if version != FORMAT:
        raise ValueError(f"RRCE version {version}, expected {FORMAT}")
    i, groups = 12, []
    for _ in range(n):
        ln = struct.unpack_from("<I", d, i)[0]
        key = d[i + 4:i + 4 + ln].decode("ascii")
        i += 4 + ln
        k = struct.unpack_from("<I", d, i)[0]
        groups.append((key, list(struct.unpack_from(f"<{k}I", d, i + 4))))
        i += 4 + 4 * k
    return version, groups, d[i:]


def build(version, groups, tail):
    out = bytearray(MAGIC + struct.pack("<II", version, len(groups)))
    for key, cars in groups:
        k = key.encode("ascii")
        out += struct.pack("<I", len(k)) + k + struct.pack(f"<I{len(cars)}I", len(cars), *cars)
    return bytes(out + tail)


def car_names(path=CAR_INDEX):
    with open(path, newline="", encoding="utf-8") as f:
        return {int(r["car_id"]): r["name"] for r in csv.DictReader(f)}


def check_group(key, cars, names):
    if not key.startswith(OURS) or not key.isascii() or len(key) > 64 or not key.replace("_", "").isalnum():
        raise ValueError(f"{key}: our groups are named {OURS}... (letters, digits, _; at most 64)")
    if not CARS_MIN <= len(cars) <= CARS_MAX:
        raise ValueError(f"{key}: {len(cars)} cars; a group has {CARS_MIN}-{CARS_MAX}")
    if len(set(cars)) != len(cars):
        raise ValueError(f"{key}: a car is listed twice")
    bad = [c for c in cars if c not in names]
    if bad:
        raise ValueError(f"{key}: car id(s) {bad} not in tables/car-index.csv")


def set_groups(groups, ours, names):
    """EA's groups unchanged and in place; ours (an ordered {key: cars})
    after them, in that order. A key of EA's can't be set."""
    ea = [(k, c) for k, c in groups if not k.startswith(OURS)]
    for key, cars in ours.items():
        if any(k == key for k, _ in ea):
            raise ValueError(f"{key}: EA's group, not ours")
        check_group(key, cars, names)
    return ea + list(ours.items())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--lib", default=LIB, help="develified lib, for the .nct key")
    ap.add_argument("--cars-csv", default=CAR_INDEX, help="tables/car-index.csv")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list")
    p.add_argument("src")
    for name in ("add", "remove", "apply"):
        p = sub.add_parser(name)
        p.add_argument("src")
        p.add_argument("dst")
        if name != "apply":
            p.add_argument("--group", required=True)
        if name == "add":
            p.add_argument("--cars", required=True, help="car ids, comma separated")
        if name == "apply":
            p.add_argument("--groups", default=GROUPS_FILE, help="our groups, {KEY: [car ids]}")
    a = ap.parse_args(argv)
    try:
        d, enc = load(a.src, a.lib)
        version, groups, tail = parse(d)
        names = car_names(a.cars_csv)
        if a.cmd == "list":
            for key, cars in groups:
                mark = " (ours)" if key.startswith(OURS) else ""
                print(f"{key}{mark}: " + ", ".join(f"{c} {names.get(c, '?')}" for c in cars))
            print(f"{len(groups)} groups, {sum(k.startswith(OURS) for k, _ in groups)} ours", file=sys.stderr)
            return 0
        ours = {k: c for k, c in groups if k.startswith(OURS)}
        if a.cmd == "add":
            ours[a.group] = [int(x) for x in a.cars.split(",") if x.strip()]
        elif a.cmd == "remove":
            if a.group not in ours:
                raise ValueError(f"{a.group}: not one of our groups in {a.src}")
            del ours[a.group]
        else:
            wanted = json.load(open(a.groups, encoding="utf-8"))
            ours = {k: [int(c) for c in v] for k, v in wanted.items() if not k.startswith("_")}
        new = set_groups(groups, ours, names)
        save(a.dst, build(version, new, tail), enc, a.lib)
        print(f"{a.dst}: {len(new)} groups ({len(ours)} ours: {', '.join(ours) or 'none'}), "
              f"{'encrypted' if enc else 'decrypted'}")
        return 0
    except (OSError, ValueError, KeyError, struct.error, UnicodeDecodeError) as e:
        print(f"rr3_onlinemp.py: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
