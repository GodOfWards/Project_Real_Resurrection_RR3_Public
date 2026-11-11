#!/usr/bin/env python3
"""Make hidden and locked cars available by changing the car description
files `vehicles/data/<id>_<year>_<make>_<model>.bin.nct` (issue #600; research:
analysis/hidden-cars.md). v1. For the server's asset update, no lib patch.

Each car file is read by CarDesc::load (0xc645a0, version 0x47 only) in one
pass. Two things in it hide or lock a car:

  part `dates`: three s64 Unix times (0 = none)
    available from  CarDesc+0x308  -1 = never; else not buyable before it
                                   (Unlocks::AddTimeLock 0xcc7188, test 0xc67058)
    sale ends       CarDesc+0x310  once past, the car leaves the showroom
                                   unless owned (test 0xc67084)
    reveal          CarDesc+0x318  hidden until then (test 0xc670a0)
  All three are compared with the game's "now" (0x14163f4). On 2026-11-10,
  51 cars have an expired sale (NASCAR, Supercars) and 3 WRC cars are not
  revealed until 2027-10-01. `dates` sets every date that hides or locks a
  car to 0: a past sale end, a future reveal, a future or "never"
  available-from (a date already passed stays as it is).

  part `locks`: the unlock requirement string (CarDesc+0x118),
    `TYPE:id[;TYPE:id]^GAMETEXT_...`, parsed by 0xcc6e9c. Each type adds locks the car
    must pass (Unlocks::AddOverride_*): QUEST (quest checks), LTS (stream
    finished), ROUND (round time passed), GAUNTLET (gauntlet complete),
    PRIZEONLY (never: prize only). NOTLOCKED adds a lock that always passes.
    `locks` empties the string when every type it names is one of the chosen
    types (default every locking type, --lock-types; a string that also
    names another type is left as it is), so the car gets the locks of a car with no
    requirement (159 of EA's cars have none). The car keeps its own price.

  rr3_car_unlocks.py list DIR [--csv OUT] [--all]
  rr3_car_unlocks.py patch DIR OUT [--parts dates,locks] [--lock-types T,..]
                                   [--cars ID,..]
  rr3_car_unlocks.py check DIR

DIR holds the car files (`*.bin.nct` as on the phone, or decrypted `*.bin`),
e.g. a copy of `.depot/vehicles/data/`. `patch` writes only the changed cars
to OUT/vehicles/data/ under their own names, encrypted like the input, so
OUT is ready to be a CC `--asset-update` (or `--asset-test`) folder. Only the
three dates (8 bytes each) and the requirement string change. The key comes
from the develified lib (--lib). Keep the originals.
"""
import argparse
import csv
import datetime
import glob
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rr3_nct  # noqa: E402

VERSION = "1"
LIB = os.path.join(HERE, "..", "game", "develified-libRealRacing3.so.gz")
FORMAT = 0x47
LOCK_TYPES = ("QUEST", "LTS", "ROUND", "GAUNTLET", "PRIZEONLY")
ALL_TYPES = LOCK_TYPES + ("NOTLOCKED",)
PARTS = ("dates", "locks")
NAME = re.compile(r"^(\d+)_\d{4}_.+\.bin(\.nct)?$")
UTC = datetime.timezone.utc


class Reader:
    def __init__(self, b):
        self.b, self.p = b, 0

    def u32(self):
        v = struct.unpack_from("<i", self.b, self.p)[0]
        self.p += 4
        return v

    def s64(self):
        v = struct.unpack_from("<q", self.b, self.p)[0]
        self.p += 8
        return v

    def skip(self, n):
        self.p += 4 * n

    def string(self):
        at = self.p
        n = self.u32()
        if not 0 <= n < 4096 or self.p + n > len(self.b):
            raise ValueError(f"bad string length {n} at {at:#x}")
        v = self.b[self.p:self.p + n].decode("latin1")
        self.p += n
        return at, v


def parse(b):
    """Read a decrypted car file as CarDesc::load does, up to the prices.
    Returns the fields this tool uses and their offsets."""
    r = Reader(b)
    if r.u32() != FORMAT:
        raise ValueError("not a version 0x47 car file")
    c = {"id": r.u32()}
    c["year"], c["make"], c["model"] = (r.string()[1] for _ in range(3))
    r.skip(1)                                   # +0x50
    r.string()                                  # +0x58 Prod/Race/Supercar
    r.skip(5 + 2 + 6)                           # +0x70, +0x74, +0x5dc, 2 bitsets, +0x368/+0x36c, 6 floats
    for _ in range(4):
        r.string()                              # drive, 3 engine sounds
    r.skip(4)
    for _ in range(2):
        r.string()
    r.skip(3)
    for _ in range(6):
        r.string()
    r.skip(12)
    for _ in range(2):
        r.string()
    r.skip(4)
    for _ in range(2):                          # 0xc66ac4: u32 n, n x (str, str)
        n = r.u32()
        if not 0 <= n < 1000:
            raise ValueError(f"bad pair count {n}")
        for _ in range(2 * n):
            r.string()
    r.skip(1)
    r.string()
    r.string()
    gears = r.u32()
    r.skip(11)
    if not 0 <= gears < 32:
        raise ValueError(f"bad gear count {gears}")
    r.skip(gears)
    r.skip(1)
    r.string()                                  # +0x5e0
    c["req_at"], c["requirement"] = r.string()  # +0x118
    r.skip(1)                                   # bool +0x130
    c["avail_at"] = r.p
    c["avail"] = r.s64()                        # +0x308
    r.skip(1)
    r.string()                                  # +0x140
    c["expire_at"] = r.p
    c["expire"] = r.s64()                       # +0x310
    c["reveal_at"] = r.p
    c["reveal"] = r.s64()                       # +0x318
    c["price_r"], _, c["price_m"], c["price_gold"] = struct.unpack_from("<4i", b, r.p)
    return c


TYPE_RE = re.compile(r"(GAUNTLET|QUEST|LTS|ROUND|PRIZEONLY|NOTLOCKED):")


def req_types(req):
    """The types named in a requirement string: `TYPE:id` entries joined by
    `;`, one `^GAMETEXT_...` text at the end (one EA car has two texts)."""
    return [m.group(1) for m in TYPE_RE.finditer(req)]


def clears(req, lock_types):
    """True when `locks` empties this string: it names a locking type and
    every type it names is in lock_types (mixed strings are left alone)."""
    t = req_types(req)
    return bool(t) and any(x in LOCK_TYPES for x in t) and all(x in lock_types for x in t)


def state(c, now):
    if c["reveal"] > now:
        return "not revealed yet"
    if 0 < c["expire"] <= now:
        return "sale expired"
    if c["avail"] == -1:
        return "never"
    if c["avail"] > now:
        return "locked until date"
    return "open" if not (c["avail"] or c["expire"] or c["reveal"]) else "open (date passed)"


def fmt(t):
    if t == -1:
        return "never"
    return "" if t == 0 else datetime.datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%d")


class Car:
    def __init__(self, path, lib_bytes):
        self.path, self.name = path, os.path.basename(path)
        raw = open(path, "rb").read()
        self.encrypted = self.name.endswith(".nct")
        self.data = rr3_nct.crypt(raw, lib_bytes) if self.encrypted else raw
        self.c = parse(self.data)


def load_dir(d, lib):
    lib_bytes = rr3_nct.read_lib(lib)
    cars = []
    for p in sorted(glob.glob(os.path.join(d, "*"))):
        if NAME.match(os.path.basename(p)):
            cars.append(Car(p, lib_bytes))
    if not cars:
        sys.exit(f"no car files (<id>_<year>_..._.bin[.nct]) in {d}")
    ids = [c.c["id"] for c in cars]
    if len(set(ids)) != len(ids):
        sys.exit("duplicate car ids in " + d)
    return cars, lib_bytes


def now_ts(args):
    if args.now:
        return int(datetime.datetime.strptime(args.now, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())
    return int(datetime.datetime.now(UTC).timestamp())


def new_dates(c, now):
    """The three dates with every hiding or locking one set to 0."""
    a, e, r = c["avail"], c["expire"], c["reveal"]
    if a == -1 or a > now:
        a = 0
    if e:
        e = 0          # a sale end in the past hides the car, one ahead will
    if r > now:
        r = 0
    return a, e, r


def change(car, parts, lock_types, now):
    """Changed decrypted bytes, or None if nothing changes."""
    c, b = car.c, bytearray(car.data)
    if "dates" in parts:
        for key, v in zip(("avail", "expire", "reveal"), new_dates(c, now)):
            struct.pack_into("<q", b, c[key + "_at"], v)
    if "locks" in parts and clears(c["requirement"], lock_types):
        at, old = c["req_at"], c["requirement"].encode("latin1")
        b[at:at + 4 + len(old)] = struct.pack("<I", 0)   # dates are after: written first
    b = bytes(b)
    return None if b == car.data else b


def cmd_list(args):
    cars, _ = load_dir(args.dir, args.lib)
    now = now_ts(args)
    rows = []
    for car in cars:
        c = car.c
        st = state(c, now)
        if not args.all and st == "open" and not clears(c["requirement"], LOCK_TYPES):
            continue
        rows.append([c["id"], f'{c["year"]} {c["make"]} {c["model"]}', fmt(c["avail"]),
                     fmt(c["expire"]), fmt(c["reveal"]), st, c["requirement"].split("^")[0],
                     c["price_r"], c["price_m"], c["price_gold"]])
    rows.sort(key=lambda r: r[0])
    head = ["car_id", "name", "available_from", "sale_ends", "reveal", "state",
            "requirement", "price_r", "price_m", "price_gold"]
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(head)
            w.writerows(rows)
        print(f"wrote {len(rows)} cars to {args.csv}")
        return
    for r in rows:
        print(f"{r[0]:>4}  {r[5]:<18} {r[2]:<10} {r[3]:<10} {r[4]:<10} {r[6]:<40} {r[1]}")
    print(f"{len(rows)} of {len(cars)} cars")


def cmd_patch(args):
    parts = [p for p in args.parts.split(",") if p]
    bad = [p for p in parts if p not in PARTS]
    if bad or not parts:
        sys.exit(f"--parts: choose from {','.join(PARTS)}")
    lock_types = [t for t in args.lock_types.split(",") if t]
    bad = [t for t in lock_types if t not in LOCK_TYPES]
    if bad:
        sys.exit(f"--lock-types: unknown {','.join(bad)} (choose from {','.join(LOCK_TYPES)})")
    cars, lib_bytes = load_dir(args.dir, args.lib)
    only = None
    if args.cars:
        only = {int(x) for x in args.cars.split(",")}
        unknown = only - {c.c["id"] for c in cars}
        if unknown:
            sys.exit("--cars: no such car " + ",".join(map(str, sorted(unknown))))
    now = now_ts(args)
    out = os.path.join(args.out, "vehicles", "data")
    os.makedirs(out, exist_ok=True)
    n = 0
    for car in cars:
        if only is not None and car.c["id"] not in only:
            continue
        b = change(car, parts, lock_types, now)
        if b is None:
            continue
        parse(b)                                  # still reads as the game reads it
        with open(os.path.join(out, car.name), "wb") as f:
            f.write(rr3_nct.crypt(b, lib_bytes) if car.encrypted else b)
        n += 1
    print(f"car-unlocks v{VERSION} ({'+'.join(parts)}): wrote {n} car file(s) to {out}")


def cmd_check(args):
    cars, _ = load_dir(args.dir, args.lib)
    now = now_ts(args)
    hidden = [c.c["id"] for c in cars if state(c.c, now) not in ("open", "open (date passed)")]
    locked = [c.c["id"] for c in cars if clears(c.c["requirement"], LOCK_TYPES)]
    print(f"{len(cars)} car files; hidden by a date: {len(hidden)}; "
          f"with a locking requirement: {len(locked)}")
    if hidden:
        print("  hidden: " + ",".join(map(str, hidden)))
    if locked:
        print("  locked: " + ",".join(map(str, locked)))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lib", default=LIB, help="develified lib for the .nct key")
    ap.add_argument("--now", help="YYYY-MM-DD instead of today (UTC), for the date states")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list")
    p.add_argument("dir")
    p.add_argument("--csv")
    p.add_argument("--all", action="store_true", help="also open cars with no requirement")
    p = sub.add_parser("patch")
    p.add_argument("dir")
    p.add_argument("out")
    p.add_argument("--parts", default="dates,locks")
    p.add_argument("--lock-types", default=",".join(LOCK_TYPES))
    p.add_argument("--cars", help="only these car ids (comma list)")
    p = sub.add_parser("check")
    p.add_argument("dir")
    args = ap.parse_args()
    {"list": cmd_list, "patch": cmd_patch, "check": cmd_check}[args.cmd](args)


if __name__ == "__main__":
    main()
