#!/usr/bin/env python3
"""Build tables/event-index.csv from a decrypted events.dat (see rr3_nct.py).

Layout, from the events.dat loader at 0xc74fb8 in libRealRacing3.so (v14.0.1):
header "RRCE", version 0x82, other tables, the series list, then a u32 tier
count and the tiers. Tier reader 0xc6da90, event reader 0xc678b8. Strings are
u32 length + bytes, bools one byte.

The tier list start is found by scanning for a count whose tiers all parse.
Series names are the series' text keys (e.g. SERIES_TITLE_JAPANESE_SPORT_SHOWDOWN):
the first "u32 series id + key" match before the tier list. The game's
translated names live in another file.

Usage:
  rr3_event_index.py EVENTS_DAT OUT_CSV
"""
import collections
import csv
import re
import struct
import sys


class Reader:
    def __init__(self, p, o):
        self.p, self.o = p, o

    def u32(self):
        v = struct.unpack_from("<i", self.p, self.o)[0]
        self.o += 4
        return v

    def f32(self):
        self.o += 4

    def u8(self):
        self.o += 1
        return self.p[self.o - 1]

    def bool(self):
        v = self.u8()
        if v > 1:
            raise ValueError(f"bad bool at {self.o - 1:#x}")
        return v

    def str(self):
        n = self.u32()
        if not 0 <= n < 4096:
            raise ValueError(f"bad string length at {self.o - 4:#x}")
        self.o += n
        return self.p[self.o - n:self.o].decode("latin1")


def read_event(r):
    e = {"type": r.u32(), "id": r.u32(), "track": r.str(), "laps": r.u32()}
    for _ in range(6):
        r.u32()
    e["options"] = r.str()
    r.u8(); r.u32(); r.str()
    r.u32(); r.u32(); r.f32(); r.u32(); r.f32(); r.str(); r.u32(); r.f32(); r.str()
    r.bool(); r.bool(); r.u32()
    if r.bool():
        r.u8(); r.f32(); r.f32()
    r.u32(); r.u32(); r.f32(); r.u32(); r.bool(); r.bool(); r.u32(); r.bool(); r.bool()
    r.u32(); r.u32(); r.u32(); r.u32(); r.bool()
    return e


def read_tier(r):
    t = {"name": r.str(), "name2": r.str()}
    r.u32()
    t["id"], t["series"] = r.u32(), r.u32()
    r.u32(); r.u32(); r.bool()
    pairs = r.u32()
    if not 0 <= pairs < 1000:
        raise ValueError("bad pair count")
    for _ in range(pairs):
        r.u32(); r.u8()
    t["sponsor"] = r.str()
    r.str(); r.str()
    n = r.u32()
    if not 0 <= n < 2000:
        raise ValueError("bad event count")
    t["events"] = [read_event(r) for _ in range(n)]
    return t


def find_tiers(p):
    for o in range(0, len(p) - 8):
        n = struct.unpack_from("<i", p, o)[0]
        if not 1000 < n < 100000 or not 0 < struct.unpack_from("<i", p, o + 4)[0] < 100:
            continue
        try:
            r = Reader(p, o + 4)
            return o, [read_tier(r) for _ in range(n)]
        except (ValueError, struct.error, IndexError):
            pass
    raise SystemExit("tier list not found")


def series_keys(p, ids, end):
    keys = {}
    for o in range(0x10, end):
        v = struct.unpack_from("<I", p, o)[0]
        if v in ids and v not in keys:
            n = struct.unpack_from("<I", p, o + 4)[0]
            if 3 < n < 120 and re.fullmatch(rb"[A-Z0-9_]+", p[o + 8:o + 8 + n]):
                keys[v] = p[o + 8:o + 8 + n].decode()
    return keys


def readable(key):
    s = re.sub(r"^(SERIES_TITLE_|STREAM_|BONUS_|EXCLUSIVE_)", "", key)
    s = re.sub(r"(_SERIES)?_TITLE$", "", s)
    return s.replace("_", " ").title()


def main():
    p = open(sys.argv[1], "rb").read()
    if p[:4] != b"RRCE":
        raise SystemExit("not a decrypted events.dat (expected RRCE magic)")
    start, tiers = find_tiers(p)
    keys = series_keys(p, {t["series"] for t in tiers}, start)
    rows = []
    for t in tiers:
        key = keys.get(t["series"], "")
        for n, e in enumerate(t["events"], 1):
            rows.append((e["id"], t["series"], key, readable(key) if key else "", t["id"], n,
                         e["track"], e["laps"], e["type"]))
    rows.sort()
    with open(sys.argv[2], "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["event_id", "series_id", "series_key", "series_name", "tier_id", "event_no",
                    "track", "laps", "type"])
        w.writerows(rows)
    print(f"{len(tiers)} tiers at {start:#x}, {len(rows)} events, "
          f"{len({t['series'] for t in tiers})} series ({len(keys)} named)")


if __name__ == "__main__":
    main()
