#!/usr/bin/env python3
"""List or reset per-event career progress in RR3 character.2.dat.

Progress lives in m_careerProgress.m_mEventProgress: a map from event id to a
record (m_bestResult, m_bestScore, m_bestRaceTime, m_completionTime, m_bCompleted,
...). Only the first `size` entries are live. Resetting writes the same state the game itself leaves on a re-opened event:
results and times zeroed, m_bCompleted = 0, m_bPreviouslyCompleted = 1. Reset
events are also removed from m_nSeenEvents so the game marks them "new".

Series and tier come from tables/event-index.csv (rr3_event_index.py, built from
the game's data/events.dat.nct).

Usage:
  rr3_events.py list FILE [--recent N] [--event ID ...] [--series ID ...] [--tier ID ...]
  rr3_events.py series FILE                     (played events per series)
  rr3_events.py reset IN OUT [--event ID ...] [--series ID ...] [--tier ID ...]
                            [--all] [--keep-series ID ...]
"""
import argparse
import collections
import csv
import datetime
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rr3_dat import load, xor, leb128  # noqa: E402
from rr3_wallet import fix_checksum  # noqa: E402

RESET = {"m_bestResult": 0, "m_bestScore": 0, "m_bestRaceTime": 0, "m_completionTime": 0,
         "m_bCompleted": False, "m_bPreviouslyCompleted": True}


def field_names(p):
    """Field id -> name, including IDX:[n] array slots. Returns (names, data offset)."""
    n = struct.unpack(">I", p[12:16])[0]
    o, names = 0x14, {}
    for _ in range(n):
        e = o
        while p[e] not in (0, 1):
            e += 1
        name = p[o:e].decode("latin1")
        if p[e] == 0:
            v, o = leb128(p, e + 1)
            names[v] = name
        else:
            c, o = leb128(p, e + 1)
            for _ in range(c):
                i, o = leb128(p, o)
                v, o = leb128(p, o)
                names.setdefault(v, name.replace("[id]", f"[{i}]"))
    return names, o


def record(p, o):
    """One value record: (key, type, value, start, value_start, end).

    key: u16 BE field id, plus 2 extra bytes when the high bit is set.
    type: low 3 bits 0 = bool/small (t>>3), 1 = int (t>>3, or LEB128 when t&0x80),
    2 = float32 LE, 3 = C string, 4 = object ref (LEB128), 5 = u32 BE length + bytes.
    """
    s = o
    k = int.from_bytes(p[o:o + 2], "big")
    o += 4 if k & 0x8000 else 2
    vs, t = o, p[o]
    o += 1
    lo = t & 7
    if lo == 1 and t & 0x80:
        v, o = leb128(p, o)
    elif lo in (0, 1):
        v = t >> 3
    elif t == 2:
        v, o = struct.unpack("<f", p[o:o + 4])[0], o + 4
    elif t == 3:
        e = p.index(0, o)
        v, o = p[o:e].decode("latin1"), e + 1
    elif t == 4:
        v, o = leb128(p, o)
        v = ("ref", v)
    elif t == 5:
        n = int.from_bytes(p[o:o + 4], "big")
        v, o = bytes(p[o + 4:o + 4 + n]), o + 4 + n
    else:
        raise ValueError(f"unknown value type {t:#x} at {s:#x}")
    return k, t, v, s, vs, o


def objects(p, data):
    """Object 0 is the root; a ref r points at objects[r + 1]. Each object = u32 count + records."""
    objs, o = [], data

    def one(o):
        n = int.from_bytes(p[o:o + 4], "big")
        o += 4
        recs = []
        for _ in range(n):
            r = record(p, o)
            recs.append(r)
            o = r[5]
        return recs, o

    root, o = one(o)
    objs.append(root)
    count = int.from_bytes(p[o:o + 4], "big")
    o += 4
    for _ in range(count):
        recs, o = one(o)
        objs.append(recs)
    if o != len(p) - 1:
        raise ValueError(f"parse ended at {o:#x}, expected {len(p) - 1:#x}")
    return objs


def event_progress(p):
    """Yield (event id, {field: (value, record)}) for every m_mEventProgress entry."""
    names, data = field_names(p)
    objs = objects(p, data)
    root = {names.get(r[0]): r for r in objs[0]}
    emap = {names.get(r[0]): r for r in objs[root["m_careerProgress.m_mEventProgress"][2][1] + 1]}
    # Only the first `size` slots are live; the slots after them are stale leftovers
    # (the store keeps keys that a later, smaller save no longer writes).
    size = emap["size"][2]
    keys = objs[emap["keys"][2][1] + 1][:size]
    vals = objs[emap["values"][2][1] + 1][:size]
    for k, v in zip(keys, vals):
        recs = objs[v[2][1] + 1]
        yield k[2], {names[r[0]]: (r[2], r) for r in recs}


def seen_events(p):
    """Live m_nSeenEvents slots: [(event id, record)]; the event shows "new" when absent."""
    names, data = field_names(p)
    objs = objects(p, data)
    root = {names.get(r[0]): r for r in objs[0]}
    recs = objs[root["m_careerProgress.m_nSeenEvents"][2][1] + 1]
    size = recs[0]
    assert names.get(size[0]) == "size"
    return size, [(r[2], r) for r in recs[1:size[2] + 1]]


def encode(t, value):
    if isinstance(value, bool):
        return bytes([8 if value else 0])
    if value < 16:
        return bytes([(value << 3) | 1])
    out = bytearray([0x81])
    while True:
        b = value & 0x7F
        value >>= 7
        out.append(b | (0x80 if value else 0))
        if not value:
            return bytes(out)


def when(minutes):
    return (datetime.datetime(1970, 1, 1) + datetime.timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M") if minutes else "-"


def load_index():
    """event id -> row of tables/event-index.csv (built by rr3_event_index.py), or {}."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tables", "event-index.csv")
    if not os.path.exists(path):
        return {}
    with open(path, newline="") as f:
        return {int(r["event_id"]): r for r in csv.DictReader(f)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "series", "reset"])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--event", type=int, nargs="+", default=[])
    ap.add_argument("--series", type=int, nargs="+", default=[], help="series ids (see the series command)")
    ap.add_argument("--tier", type=int, nargs="+", default=[], help="tier ids")
    ap.add_argument("--all", action="store_true", help="reset every played event")
    ap.add_argument("--keep-series", type=int, nargs="+", default=[], help="series ids to leave alone")
    ap.add_argument("--recent", type=int, help="list the N most recently completed events")
    a = ap.parse_args()
    p = bytearray(load(a.files[0]))
    entries = list(event_progress(p))
    index = load_index()

    def selected(ev):
        row = index.get(ev, {})
        return (ev in a.event or int(row.get("series_id", -1)) in a.series
                or int(row.get("tier_id", -1)) in a.tier)

    if a.cmd == "series":
        groups = {}
        for ev, f in entries:
            row = index.get(ev)
            key = (int(row["series_id"]), row["series_name"]) if row else (-1, "(not in index)")
            g = groups.setdefault(key, [0, 0])
            g[0] += 1
            g[1] += f["m_bCompleted"][0]
        total = collections.Counter(int(r["series_id"]) for r in index.values())
        print(f"{'series':>6}  {'played':>6} {'done':>4} {'events':>6}  name")
        for (sid, name), (played, done) in sorted(groups.items()):
            print(f"{sid:>6}  {played:>6} {done:>4} {total.get(sid, 0):>6}  {name}")
        return

    if a.cmd == "list":
        filtered = a.event or a.series or a.tier
        rows = [e for e in entries if not filtered or selected(e[0])]
        if a.recent:
            rows = sorted(rows, key=lambda e: -e[1]["m_completionTime"][0])[:a.recent]
        print(f"{len(entries)} event records")
        print(f"{'event':>7} {'done':>4} {'pos':>3} {'score':>6} {'time ms':>8}  {'completed (UTC)':16}  "
              f"{'series':>6} {'tier':>6}  series name / track")
        for ev, f in rows:
            g = {k: v[0] for k, v in f.items()}
            row = index.get(ev, {})
            print(f"{ev:>7} {g['m_bCompleted']:>4} {g['m_bestResult']:>3} {g['m_bestScore']:>6} "
                  f"{g['m_bestRaceTime']:>8}  {when(g['m_completionTime']):16}  "
                  f"{row.get('series_id', '?'):>6} {row.get('tier_id', '?'):>6}  "
                  f"{row.get('series_name', '')} / {row.get('track', '')}")
        return

    if not (a.event or a.series or a.tier or a.all):
        raise SystemExit("reset needs --event, --series, --tier or --all")
    edits, found = [], set()
    for ev, f in entries:
        if not (a.all or selected(ev)) or int(index.get(ev, {}).get("series_id", -1)) in a.keep_series:
            continue
        found.add(ev)
        for name, value in RESET.items():
            _, r = f[name]
            edits.append((r[4], r[5], encode(r[1], value)))
    missing = set(a.event) - found
    if missing:
        raise SystemExit(f"no progress record for event(s): {sorted(missing)}")
    if not found:
        raise SystemExit("no played events match")
    # Drop the reset events from the seen list so they show as "new" again: rewrite the
    # live slots with the remaining ids and lower `size` (later slots are ignored).
    size, seen = seen_events(p)
    kept = [ev for ev, _ in seen if ev not in found]
    for (_, r), ev in zip(seen, kept):
        edits.append((r[4], r[5], encode(r[1], ev)))
    edits.append((size[4], size[5], encode(size[1], len(kept))))
    for vs, end, new in sorted(edits, reverse=True):
        p[vs:end] = new
    p[8:12] = struct.pack(">I", len(p))
    p[-1] = fix_checksum(p)
    list(event_progress(p))  # re-parse to make sure the result is well formed
    open(a.files[1], "wb").write(xor(bytes(p)))
    print(f"reset {len(found)} event(s): {sorted(found)}; "
          f"{len(seen) - len(kept)} removed from the seen list")


if __name__ == "__main__":
    main()
