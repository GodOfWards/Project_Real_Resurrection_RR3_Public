#!/usr/bin/env python3
"""List the events that use fuel consumption (see docs/details/fuel-consumption-details.md).

Reads a decrypted events.dat (rr3_nct.py) and writes one CSV row per event whose
options string sets Fuel or ConsumptionRate. The game attaches the fuel rule
set to any event with a "Fuel" option, and always to "Fuel" type events.

Usage:
  rr3_fuel.py EVENTS_DAT OUT_CSV
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rr3_event_index as ei  # noqa: E402

# Event type names, from the string -> type function at 0xc68978.
TYPES = ["Elimination", "H2H", "Cup", "HotLaps", "Endurance", "SpearASpud", "BellRing",
         "SpeedRecord", "ConeChallenge", "Autocross", "SpeedSnap", "DragRace", "Hunter",
         "TimeTrial", "Fuel", "NASCAR", "SpeedGate"]


def parse_options(s):
    opts = {}
    for part in s.split(";"):
        k, _, v = part.partition(":")
        if k.strip():
            opts[k.strip()] = v.strip()
    return opts


def num(s, default=None):
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


def main():
    p = open(sys.argv[1], "rb").read()
    if p[:4] != b"RRCE":
        raise SystemExit("not a decrypted events.dat (expected RRCE magic)")
    start, tiers = ei.find_tiers(p)
    keys = ei.series_keys(p, {t["series"] for t in tiers}, start)
    rows = []
    for t in tiers:
        key = keys.get(t["series"], "")
        for n, e in enumerate(t["events"], 1):
            o = parse_options(e["options"])
            if e["type"] != 14 and "Fuel" not in o and "ConsumptionRate" not in o:
                continue
            # Defaults from the RuleSet_Fuel constructor (0x101ce50).
            fuel = num(o.get("Fuel"), 120.0)
            rate = num(o.get("ConsumptionRate"), 0.0001)
            slip = num(o.get("SlipstreamingConsumptionRate"), rate)
            ty = TYPES[e["type"]] if 0 <= e["type"] < len(TYPES) else str(e["type"])
            rows.append((e["id"], t["series"], ei.readable(key) if key else "", t["id"], n,
                         e["track"], e["laps"], ty, f"{fuel:g}", f"{rate:g}", f"{slip:g}",
                         int("SlipstreamingEnabled" in o),
                         f"{fuel / rate:.0f}" if rate > 0 else "", e["options"]))
    rows.sort()
    with open(sys.argv[2], "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["event_id", "series_id", "series_name", "tier_id", "event_no", "track",
                    "laps", "type", "fuel", "consumption_rate", "slipstream_rate",
                    "slipstreaming", "throttle_seconds", "options"])
        w.writerows(rows)
    print(f"{len(rows)} fuel events")


if __name__ == "__main__":
    main()
