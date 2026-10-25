#!/usr/bin/env python3
"""List garage cars in RR3 character.2.dat and switch their VIP flag.

Cars live in m_garage.m_cars: slots IDX:[n].*m_pCar (a car object) plus
IDX:[n].m_nTimesRaced / m_nTimesWon. Only the first m_garage.nCarCount slots are
live; the slots after them are stale leftovers (same pattern as event progress).

Per car: m_carDescId (the car's id in the game data), m_bEnabled, upgrade stages
(m_PowerPlayerState.m_Upgrades.m_upgradeCurrentStage, one entry per upgrade
category) and the VIP flag m_PowerPlayerState.m_Upgrades.m_bVIPService.

Small ints (type byte with low bits 001 and no 0x80) appear to store value + 1:
a 5-entry list has size 6, unset timers are 1. `list` shows the stored value
minus 1 for those; LEB128 ints are shown as stored.

Owning a car = a live slot with m_bEnabled set (Tom's garage count matches the
enabled live slots). `own` gives a car that only has a stale slot: it swaps that
slot, and the car's m_garage.m_customisationInventory entry (also live up to
nInventoryCount), into the first stale position and raises both counts by one.
The car arrives as the stale copy (in saves built on the community save: fully
upgraded and VIP); --stock resets its upgrades, `vip --off` removes VIP. Cars with no slot at all cannot be added this way.

Car names come from tables/car-index.csv (from the game's cardesc.list.nct).

Usage:
  rr3_cars.py find TEXT ...              (search the car index by name or id, no save needed)
  rr3_cars.py list FILE [--all]          (--all also shows stale slots)
  rr3_cars.py vip IN OUT (--car ID ... | --all) [--off]
  rr3_cars.py own IN OUT --car ID ... [--stock]   (--stock: arrive with no upgrades)
  rr3_cars.py stock IN OUT --car ID ...           (reset upgrades of owned cars; VIP kept)
"""
import csv
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rr3_dat import load, xor  # noqa: E402
from rr3_events import encode, field_names, objects  # noqa: E402
from rr3_wallet import fix_checksum  # noqa: E402


def num(r):
    """Decoded int of a record: small ints are stored as value + 1."""
    t, v = r[1], r[2]
    return v - 1 if t & 7 == 1 and not t & 0x80 else v


def load_names():
    """car id -> name from tables/car-index.csv, or {}."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tables", "car-index.csv")
    if not os.path.exists(path):
        return {}
    with open(path, newline="") as f:
        return {int(r["car_id"]): r["name"] for r in csv.DictReader(f)}


def garage(p):
    """(names, objects, root records by name)."""
    names, data = field_names(p)
    objs = objects(p, data)
    return names, objs, {names.get(r[0]): r for r in objs[0]}


def cars(p):
    """Yield dicts for every m_garage.m_cars slot, in slot order."""
    names, objs, root = garage(p)
    live = root["m_garage.nCarCount"][2]
    # Slots are record triples (car, times raced, times won) in slot order. Go by
    # position: array slot ids are shared between tables, so in some saves the name
    # table resolves them to another table's prefix (EVTID:[..], TIER_[..]).
    recs = objs[root["m_garage.m_cars"][2][1] + 1]
    slots = {i // 3 + 1: dict(zip(("*m_pCar", "m_nTimesRaced", "m_nTimesWon"), recs[i:i + 3]))
             for i in range(0, len(recs), 3)}
    for n, s in sorted(slots.items()):
        car = {names[r[0]]: r for r in objs[s["*m_pCar"][2][1] + 1]}
        up = {names[r[0]]: r for r in objs[car["m_PowerPlayerState.m_Upgrades"][2][1] + 1]}
        stage_recs = objs[up["m_upgradeCurrentStage"][2][1] + 1]
        stages = [num(r) for r in stage_recs
                  if names[r[0]].startswith("IDX:")]
        yield {"slot": n, "live": n <= live, "car": num(car["m_carDescId"]),
               "enabled": car["m_bEnabled"][2], "enabled_rec": car["m_bEnabled"], "recs": list(s.values()), "vip": up["m_bVIPService"],
               "stage_recs": stage_recs,
               "stages": stages, "raced": num(s["m_nTimesRaced"]), "won": num(s["m_nTimesWon"])}


def own(p, car):
    """Make one car owned, editing p in place. Returns a summary line."""
    rows = list(cars(p))
    src = next((r for r in rows if r["car"] == car), None)
    if src is None:
        raise SystemExit(f"car {car} has no slot in this save; it cannot be added this way")
    if src["live"] and src["enabled"]:
        return f"car {car} is already owned"
    names, objs, root = garage(p)
    edits = []
    if not src["enabled"]:
        r = src["enabled_rec"]
        edits.append((r[4], r[5], b"\x08"))
    if not src["live"]:
        live, ninv = root["m_garage.nCarCount"][2], root["m_garage.nInventoryCount"][2]
        # Swap the value bytes of the car's slot and the first stale slot; keys stay put.
        for x, y in zip(src["recs"], rows[live]["recs"]):
            edits += [(x[4], x[5], bytes(p[y[4]:y[5]])), (y[4], y[5], bytes(p[x[4]:x[5]]))]
        # Same for its customisation inventory entry (matched by m_nCarId).
        inv = objs[root["m_garage.m_customisationInventory"][2][1] + 1]
        per = len(inv) // len(rows)
        groups = [inv[i:i + per] for i in range(0, len(inv), per)]
        gi = next((i for i, g in enumerate(groups) if num(g[0]) == car), None)
        if gi is not None and gi >= ninv:
            for x, y in zip(groups[gi], groups[ninv]):
                edits += [(x[4], x[5], bytes(p[y[4]:y[5]])), (y[4], y[5], bytes(p[x[4]:x[5]]))]
            ninv += 1
        for key, value in (("m_garage.nCarCount", live + 1), ("m_garage.nInventoryCount", ninv)):
            r = root[key]
            edits.append((r[4], r[5], encode(r[1], value)))
    for vs, end, new in sorted(edits, reverse=True):
        p[vs:end] = new
    assert any(r["live"] and r["enabled"] and r["car"] == car for r in cars(p))
    return f"car {car} now owned" + ("" if src["live"] else " (moved in from a stale slot)")


def stock(p, car):
    """Undo every upgrade of one live car (levels and pending timers to 0); VIP is untouched."""
    r = next((r for r in cars(p) if r["live"] and r["car"] == car), None)
    if r is None:
        raise SystemExit(f"car {car} is not in the live garage")
    # Upgrade levels IDX:[k] and their TIME:[k]/WAIT:[k] timers: small int 0 (0x09, stored
    # as value + 1), as on a car that was never upgraded.
    for x in sorted(r["stage_recs"], key=lambda x: -x[4]):
        p[x[4]:x[5]] = b"\x09"
    assert all(v == 0 for v in next(c for c in cars(p) if c["live"] and c["car"] == car)["stages"])
    return f"car {car} upgrades reset"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["find", "list", "vip", "own", "stock"])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--car", type=int, nargs="+", default=[], help="car ids (m_carDescId)")
    ap.add_argument("--all", action="store_true", help="list: show stale slots; vip: every live car")
    ap.add_argument("--off", action="store_true", help="vip: remove VIP instead of adding it")
    ap.add_argument("--stock", action="store_true", help="own: also reset the car's upgrades")
    a = ap.parse_args()
    if a.cmd == "find":
        words = [w.lower() for w in a.files]
        for cid, name in sorted(load_names().items()):
            if all(w in f"{cid} {name}".lower() for w in words):
                print(f"{cid:>5}  {name}")
        return
    p = bytearray(load(a.files[0]))
    rows = list(cars(p))

    if a.cmd == "list":
        live = sum(r["live"] for r in rows)
        print(f"{live} live car slots ({len(rows)} slots in the file)")
        print(f"{'slot':>4} {'car':>5} {'live':>4} {'own':>3} {'vip':>3} {'raced':>5} {'won':>4}  "
              f"{'name':44} upgrade stages")
        carnames = load_names()
        for r in rows:
            if r["live"] or a.all:
                print(f"{r['slot']:>4} {r['car']:>5} {int(r['live']):>4} {r['enabled']:>3} "
                      f"{r['vip'][2]:>3} {r['raced']:>5} {r['won']:>4}  "
                      f"{carnames.get(r['car'], '?'):44} {r['stages']}")
        return

    if a.cmd == "own":
        if not a.car:
            raise SystemExit("own needs --car")
        for car in a.car:
            print(own(p, car))
            if a.stock:
                print(stock(p, car))
        p[8:12] = struct.pack(">I", len(p))
        p[-1] = fix_checksum(p)
        open(a.files[1], "wb").write(xor(bytes(p)))
        return

    if a.cmd == "stock":
        if not a.car:
            raise SystemExit("stock needs --car")
        for car in a.car:
            print(stock(p, car))
        p[8:12] = struct.pack(">I", len(p))
        p[-1] = fix_checksum(p)
        open(a.files[1], "wb").write(xor(bytes(p)))
        return

    if not (a.car or a.all):
        raise SystemExit("vip needs --car or --all")
    targets = [r for r in rows if r["live"] and (a.all or r["car"] in a.car)]
    missing = set(a.car) - {r["car"] for r in targets}
    if missing:
        raise SystemExit(f"car(s) not in the live garage: {sorted(missing)}")
    # Bools are a lone type byte: 0x08 = true, 0x00 = false; same length, so no shifting.
    for r in targets:
        p[r["vip"][4]] = 0x00 if a.off else 0x08
    p[8:12] = struct.pack(">I", len(p))
    p[-1] = fix_checksum(p)
    list(cars(p))  # re-parse to make sure the result is well formed
    open(a.files[1], "wb").write(xor(bytes(p)))
    print(f"VIP {'off' if a.off else 'on'} for {len(targets)} car(s): {[r['car'] for r in targets]}")


if __name__ == "__main__":
    main()
