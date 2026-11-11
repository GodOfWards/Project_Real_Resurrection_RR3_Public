#!/usr/bin/env python3
"""List or change Weekly Time Trial and other LTS dates in data/events.dat.nct
(design #191, part B; #311). v7: `lts` puts every moved LTS on Tuesdays
00:00 UTC in whole weeks (#574; --lts-version 1 keeps EA's times); v6: `prizes` writes the WTT prize table
the server's prize list reads (rr3_cc_server.py v5.76 --prize-events,
#193); v5: `cars` sets the allowed cars of a WTT
(#191 car-swap test); v4: `lts` moves the other LTS (plain, TTC,
Seasons) as rr3_wtt.py v2 does in the lib (#311, design #306); v3: `plan`
builds the schedule from tables/wtt-plan.csv (pinned weeks for real races,
#191); v2: `shift` (#292).

events.dat holds the limited-time series (LTS) block read by the parser
0xc32f70 (layout: analysis/weekly-time-trial.md section 1.1). A WTT is a
record with sub type 2 and the WTT flag (+0x70) set. Its start and end are
u32 Unix times (UTC). This tool finds the LTS block (the only offset where
a count is followed by that many well-formed records), then reads or
rewrites those two numbers in place. The file keeps its size; only 8 bytes
per changed WTT differ.

  rr3_wtt_dates.py list IN [--all]
      every WTT: LTS index, start, end, event id (from analysis/wtt-schedule.csv)
  rr3_wtt_dates.py now IN OUT (--event ID | --lts-index N) [--days-left 6]
      that WTT runs from 1 day ago to DAYS_LEFT days from now (test 2)
  rr3_wtt_dates.py set IN OUT (--event ID | --lts-index N) --start "YYYY-MM-DD HH:MM" [--end ...]
      that WTT on the given UTC dates (end defaults to start + 7 days)
  rr3_wtt_dates.py shift IN OUT [--start 2026-11-17]
      every WTT that ended by 2025-12-15 20:00 UTC moves by whole weeks so
      EA's week 1 starts on START (a Tuesday), as rr3_wtt.py does in the lib;
      then `set` can pin single weeks to other dates. For the server's
      asset update (rr3_cc_server.py --asset-update, #292): every WTT in
      that file must end after the cutoff, or the lib fallback moves it again.
  rr3_wtt_dates.py lts IN OUT [--lts-start 2026-11-17] [--round-start 2026-11-17]
      every other LTS moves as rr3_wtt.py v2 does at load (same functions):
      plain LTS and TTC so EA's first LTS (2016-03-10) starts on LTS_START;
      Seasons LTS (sub type 0 with a round) so 2021_ROUND_1 (2021-01-06)
      starts on ROUND_START (the same --round-start as rr3_championships.py).
      Kept: WTTs (use `plan` or `shift`), the community LTS, end 0 (the F1
      2023 group) and records ending after 2025-12-21. For the asset update
      without a lib patch (#311): run `plan` first, then `lts` on its output.
      Don't serve it to a lib patched with rr3_wtt.py v2: harmless (the lib
      skips records that end after its cutoffs) but pointless.
      v7 (#574, Tom 2026-11-09: every rotation on Tuesday 00:00 UTC): each
      moved start and end then goes to the nearest Tuesday 00:00 UTC, and an
      LTS that would end on its start day runs one week (whole weeks, at
      least one); a record with start = end (a Seasons LTS that only marks
      when it can be started) keeps start = end. rr3_championships.py v2
      snaps the rounds the same way, so a Seasons LTS stays in its round.
      --lts-version 1 writes v6's exact shifted times.
  rr3_wtt_dates.py plan IN OUT [--plan tables/wtt-plan.csv] [--start 2026-11-17]
      the server schedule: clean weeks, Tuesday 00:00 UTC to Tuesday, from
      START. Each week in the plan file (week = its Tuesday, event_id) gets
      that WTT; every other week gets the next unused WTT in EA's order.
      Each WTT runs once, so the 384 weeks end about 7.4 years after START.
  rr3_wtt_dates.py prizes IN OUT.csv
      the prize table for rr3_cc_server.py --prize-events (v6, #193): one row
      per WTT of IN with its event id (analysis/wtt-schedule.csv), start and
      end (Unix UTC, and readable). Run it on the events.dat the server
      serves, after every change to it. TTC events are not listed (no event
      id map for them yet).
  rr3_wtt_dates.py cars IN OUT (--event ID | --lts-index N) --cars 299,350,351
      the WTT's allowed cars (its tier's car list, analysis/wtt-cars.md): the
      first car is the shown one (flag 7), the others flag 3. A different
      number of cars changes the file's size (untested in game).

IN and OUT are encrypted .nct files (as on the phone); a decrypted file
(starting with RRCE) is also accepted and written back decrypted. The key
comes from the develified lib (--lib). Never overwrite the phone's only
copy: keep a backup of the original events.dat.nct.
"""
import argparse
import csv
import datetime
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rr3_nct  # noqa: E402
import rr3_wtt  # noqa: E402  (the shift rules of the lib patch, v2)

VERSION = "7"
PLAN = os.path.join(HERE, "..", "tables", "wtt-plan.csv")
FIRST_WEEK = datetime.datetime(2018, 8, 21, tzinfo=datetime.timezone.utc)   # EA's week 1
CUTOFF = 1765828800                   # 2025-12-15 20:00 UTC, end of EA's last WTT (rr3_wtt.py)
SCHEDULE = os.path.join(HERE, "..", "analysis", "wtt-schedule.csv")
LIB = os.path.join(HERE, "..", "game", "develified-libRealRacing3.so.gz")
MAGIC = b"RRCE"
UTC = datetime.timezone.utc


KNOWN_OFFSET = 0xD9B58E    # Tom's file, md5 0a21c68abefbfcac00e7387f025e8012 (analysis section 4)


class Bad(Exception):
    pass


def parse_records(d, off):
    """Parse the LTS block at `off`. Returns a list of dicts with the file
    offsets of start and end, or raises Bad."""
    def u32(p):
        if p + 4 > len(d):
            raise Bad("end of file")
        return struct.unpack_from("<I", d, p)[0], p + 4

    def byte(p):
        if p >= len(d):
            raise Bad("end of file")
        return d[p], p + 1

    def string(p):
        n, p = u32(p)
        if n > 4096 or p + n > len(d):
            raise Bad(f"string length {n} at 0x{p - 4:x}")
        return d[p:p + n], p + n

    count, p = u32(off)
    if not 100 <= count <= 5000:
        raise Bad(f"count {count}")
    recs = []
    for n in range(count):
        key, p = u32(p)
        sub, p = u32(p)
        if sub > 2:
            raise Bad(f"record {n}: sub type {sub} at 0x{p - 4:x}")
        start_at = p
        start, p = u32(p)
        end, p = u32(p)
        _, p = byte(p)
        _, p = u32(p)                      # lead time
        for _ in range(3):
            _, p = string(p)
        _, p = u32(p)
        wtt, p = byte(p)
        _, p = byte(p)
        _, p = byte(p)
        tail = []
        for _ in range(6):
            s, p = string(p)
            tail.append(s)
        recs.append({"key": key, "sub": sub, "wtt": wtt, "start": start, "end": end, "at": start_at,
                     "round": bytes(tail[3])})          # field 17, championship round (rec +0xc0)
    return recs


def find_block(d):
    """The only offset where a count of well-formed LTS records starts.
    Records are only accepted if every WTT-looking value is sane: sub type
    0..2, WTT byte 0/1, and every sub type 2 + WTT record dated 2001..2038."""
    found = []
    for off in range(0, len(d) - 32):
        c, _, sub = struct.unpack_from("<3I", d, off)
        if not 100 <= c <= 5000 or sub > 2:
            continue
        try:
            recs = parse_records(d, off)
        except Bad:
            continue
        if all(r["wtt"] <= 1 for r in recs) and \
                all(1e9 <= r["start"] <= r["end"] < 2 ** 31 for r in recs if r["sub"] == 2 and r["wtt"]):
            found.append((off, recs))
    if len(found) != 1:
        why = ""
        if KNOWN_OFFSET + 4 <= len(d):
            try:
                parse_records(d, KNOWN_OFFSET)
                why = f"; at 0x{KNOWN_OFFSET:x} the records parse"
            except Bad as e:
                why = f"; at 0x{KNOWN_OFFSET:x}: {e}"
        sys.exit(f"expected one LTS block, found {len(found)} "
                 f"({', '.join(hex(o) for o, _ in found[:5])}){why}")
    return found[0]


def tier_cars(d, event_id):
    """(offset of the tier's car-pair count, list of (car, flag)) for the
    tier holding event_id, from tools/rr3_event_index.py's reader."""
    import rr3_event_index as X
    found = []

    def read_tier(r):
        r.str(); r.str(); r.u32(); r.u32(); r.u32(); r.u32(); r.u32(); r.bool()
        at = r.o
        n = r.u32()
        if not 0 <= n < 1000:
            raise ValueError("bad pair count")
        pairs = [(r.u32(), r.u8()) for _ in range(n)]
        r.str(); r.str(); r.str()
        m = r.u32()
        if not 0 <= m < 2000:
            raise ValueError("bad event count")
        events = [X.read_event(r) for _ in range(m)]
        if any(e["id"] == event_id for e in events):
            found.append((at, pairs))
        return {"events": events}

    X.read_tier = read_tier
    X.find_tiers(bytes(d))
    if len(found) != 1:
        sys.exit(f"event {event_id}: found in {len(found)} tiers")
    return found[0]


def load(path, lib):
    raw = open(path, "rb").read()
    if raw[:4] == MAGIC:
        return bytearray(raw), False
    d = bytearray(rr3_nct.crypt(raw, rr3_nct.read_lib(lib)))
    if d[:4] != MAGIC:
        sys.exit(f"{path}: not events.dat (no RRCE after decrypting)")
    return d, True


def save(path, d, encrypted, lib):
    open(path, "wb").write(rr3_nct.crypt(bytes(d), rr3_nct.read_lib(lib)) if encrypted else bytes(d))


def schedule():
    """lts_index -> event id, from analysis/wtt-schedule.csv."""
    try:
        return {int(r["lts_index"]): r for r in csv.DictReader(open(SCHEDULE, newline=""))}
    except OSError:
        return {}


PRIZE_FIELDS = ["event_id", "start", "end", "start_utc", "end_utc", "lts_index"]


def prize_rows(recs, sched):
    """Prize table rows (v6, #193): every WTT with a known event id, by start."""
    rows = []
    for r in recs:
        ev = sched.get(r["key"], {}).get("event_id")
        if r["sub"] == 2 and r["wtt"] and ev:
            rows.append({"event_id": int(ev), "start": r["start"], "end": r["end"],
                         "start_utc": fmt(r["start"]), "end_utc": fmt(r["end"]), "lts_index": r["key"]})
    return sorted(rows, key=lambda r: (r["start"], r["event_id"]))


def write_prizes(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PRIZE_FIELDS)
        w.writeheader()
        w.writerows(rows)


TUESDAY0 = 432000                     # 1970-01-06 00:00 UTC, a Tuesday
WEEK = 7 * 86400


def nearest_tuesday(t):
    """The nearest Tuesday 00:00 UTC (half a week rounds up), v7 (#574)."""
    return TUESDAY0 + (t - TUESDAY0 + WEEK // 2) // WEEK * WEEK


def tuesday_window(start, end):
    """(start, end) on Tuesdays 00:00 UTC in whole weeks: each to the nearest
    Tuesday; at least one week unless start = end (kept a point)."""
    s, e = nearest_tuesday(start), nearest_tuesday(end)
    if end == start:
        return s, s
    return s, max(e, s + WEEK)


def fmt(t):
    return datetime.datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%d %H:%M")


def parse_time(s):
    try:
        return int(datetime.datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=UTC).timestamp())
    except ValueError:
        sys.exit(f"time must be 'YYYY-MM-DD HH:MM' (UTC), got {s!r}")


def pick(recs, a):
    wtts = [r for r in recs if r["sub"] == 2 and r["wtt"]]
    if a.event is not None:
        keys = [k for k, r in schedule().items() if r["event_id"] == str(a.event)]
        if not keys:
            sys.exit(f"event {a.event} is not a WTT in analysis/wtt-schedule.csv")
        a.lts_index = keys[0]
    hit = [r for r in wtts if r["key"] == a.lts_index]
    if len(hit) != 1:
        sys.exit(f"no WTT with LTS index {a.lts_index} in this events.dat")
    return hit[0]


def tuesday(s, what):
    try:
        day = datetime.datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        sys.exit(f"{what} must be YYYY-MM-DD, got {s!r}")
    if day.weekday() != 1:
        sys.exit(f"{what} {s} is a {day:%A}, not a Tuesday")
    return int(day.timestamp())


def build_plan(d, off, recs, a):
    """Write the planned schedule into d (see `plan` in the usage)."""
    week = 7 * 86400
    start = tuesday(a.start, "--start")
    if start <= CUTOFF:
        sys.exit("--start must be after EA's last WTT (2025-12-15)")
    sched = schedule()
    by_event = {r["event_id"]: k for k, r in sched.items()}
    wtts = {r["key"]: r for r in recs if r["sub"] == 2 and r["wtt"]}
    pins = {}
    with open(a.plan, newline="") as f:
        for n, row in enumerate(csv.DictReader(f), 2):
            t = tuesday(row["week"].strip(), f"{a.plan} line {n}: week")
            k = by_event.get(row["event_id"].strip())
            if k is None or k not in wtts:
                sys.exit(f"{a.plan} line {n}: event {row['event_id']} is not a WTT in this events.dat")
            if t < start:
                sys.exit(f"{a.plan} line {n}: week {row['week']} is before --start")
            slot = (t - start) // week
            if slot in pins or k in pins.values():
                sys.exit(f"{a.plan} line {n}: week or event planned twice")
            pins[slot] = k
    order = [k for k in sorted(wtts, key=lambda k: (wtts[k]["start"], k)) if k not in pins.values()]
    slots = len(wtts)
    if max(pins, default=0) >= slots:
        sys.exit("a pinned week is past the end of the cycle")
    it = iter(order)
    for slot in range(slots):
        k = pins.get(slot) if slot in pins else next(it)
        t0 = start + slot * week
        if t0 + week >= 2 ** 31:
            sys.exit("the schedule runs past 2038-01-19; use an earlier --start")
        struct.pack_into("<II", d, wtts[k]["at"], t0, t0 + week)
    for slot in sorted(pins):
        ev = sched.get(pins[slot], {})
        print(f"pinned {fmt(start + slot * week)[:10]}: event {ev.get('event_id', '?')} {ev.get('track', '')}")
    print(f"{a.out}: {slots} weeks from {fmt(start)[:10]} to {fmt(start + slots * week)[:10]} UTC, "
          f"{len(pins)} pinned")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lib", default=LIB, help="develified lib, for the .nct key")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list")
    ls.add_argument("inp")
    ls.add_argument("--all", action="store_true", help="every LTS record, not only WTTs")
    for name in ("now", "set"):
        p = sub.add_parser(name)
        p.add_argument("inp")
        p.add_argument("out")
        g = p.add_mutually_exclusive_group(required=True)
        g.add_argument("--event", type=int, help="WTT event id (analysis/wtt-schedule.csv)")
        g.add_argument("--lts-index", type=int, help="LTS index (record key)")
        if name == "now":
            p.add_argument("--days-left", type=float, default=6, help="days until it ends (default 6)")
        else:
            p.add_argument("--start", required=True, help="'YYYY-MM-DD HH:MM' UTC")
            p.add_argument("--end", help="'YYYY-MM-DD HH:MM' UTC (default start + 7 days)")
    sh = sub.add_parser("shift")
    sh.add_argument("inp")
    sh.add_argument("out")
    sh.add_argument("--start", default="2026-11-17", help="Tuesday when EA's week 1 starts (default 2026-11-17)")
    lt = sub.add_parser("lts")
    lt.add_argument("inp")
    lt.add_argument("out")
    lt.add_argument("--lts-start", default=rr3_wtt.DEFAULT_START,
                    help=f"day EA's first plain LTS (2016-03-10) moves to (default {rr3_wtt.DEFAULT_START})")
    lt.add_argument("--lts-version", type=int, choices=(1, 2), default=2,
                    help="2 (default, v7): whole weeks on Tuesdays 00:00 UTC (#574); 1: EA's exact times")
    lt.add_argument("--round-start", default=rr3_wtt.DEFAULT_START,
                    help=f"day 2021_ROUND_1 (2021-01-06) moves to; the same as rr3_championships.py "
                         f"(default {rr3_wtt.DEFAULT_START})")
    pl = sub.add_parser("plan")
    pl.add_argument("inp")
    pl.add_argument("out")
    pl.add_argument("--plan", default=PLAN, help="pinned weeks (default tables/wtt-plan.csv)")
    pl.add_argument("--start", default="2026-11-17", help="Tuesday of the first week (default 2026-11-17)")
    ca = sub.add_parser("cars")
    ca.add_argument("inp")
    ca.add_argument("out")
    g = ca.add_mutually_exclusive_group(required=True)
    g.add_argument("--event", type=int, help="WTT event id")
    g.add_argument("--lts-index", type=int, help="LTS index (record key)")
    ca.add_argument("--cars", required=True, help="car ids, comma-separated (tables/car-index.csv)")
    pz = sub.add_parser("prizes")
    pz.add_argument("inp")
    pz.add_argument("out", help="CSV for rr3_cc_server.py --prize-events")
    a = ap.parse_args()

    d, encrypted = load(a.inp, a.lib)
    off, recs = find_block(d)
    if a.cmd == "list":
        sched = schedule()
        shown = recs if a.all else [r for r in recs if r["sub"] == 2 and r["wtt"]]
        print(f"LTS block at 0x{off:x}: {len(recs)} records, "
              f"{sum(1 for r in recs if r['sub'] == 2 and r['wtt'])} WTTs")
        for r in shown:
            ev = sched.get(r["key"], {})
            print(f"{r['key']:5d}  sub {r['sub']} wtt {r['wtt']}  {fmt(r['start'])} -> {fmt(r['end'])}  "
                  f"event {ev.get('event_id', '-')}  {ev.get('track', '')}")
        return

    if a.cmd == "prizes":
        rows = prize_rows(recs, schedule())
        write_prizes(a.out, rows)
        print(f"{a.out}: {len(rows)} WTTs, first starts {fmt(rows[0]['start'])}, "
              f"last ends {fmt(max(r['end'] for r in rows))} UTC" if rows else f"{a.out}: no WTT")
        return

    if a.cmd == "shift":
        try:
            day = datetime.datetime.strptime(a.start, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            sys.exit(f"--start must be YYYY-MM-DD, got {a.start!r}")
        if day.weekday() != 1:
            sys.exit(f"--start must be a Tuesday, {a.start} is a {day:%A}")
        shift = int((day - FIRST_WEEK).total_seconds())
        if shift <= CUTOFF - int(FIRST_WEEK.timestamp()):
            sys.exit("--start must be after EA's last WTT (2025-12-15)")
        moved = 0
        for r in recs:
            if r["sub"] == 2 and r["wtt"] and r["end"] <= CUTOFF:
                if r["end"] + shift >= 2 ** 31:
                    sys.exit(f"--start {a.start} pushes LTS index {r['key']} past 2038-01-19")
                struct.pack_into("<II", d, r["at"], r["start"] + shift, r["end"] + shift)
                moved += 1
        after = parse_records(d, off)
        wtt = [r for r in after if r["sub"] == 2 and r["wtt"]]
        save(a.out, d, encrypted, a.lib)
        print(f"{a.out}: {moved} WTTs moved by {shift // 604800} weeks; "
              f"first {fmt(min(r['start'] for r in wtt))}, last ends {fmt(max(r['end'] for r in wtt))} UTC")
        return

    if a.cmd == "cars":
        sched = schedule()
        if a.event is None:
            ev = sched.get(a.lts_index, {}).get("event_id")
            if ev is None:
                sys.exit(f"LTS index {a.lts_index} is not in analysis/wtt-schedule.csv")
            a.event = int(ev)
        if str(a.event) not in {r["event_id"] for r in sched.values()}:
            sys.exit(f"event {a.event} is not a WTT in analysis/wtt-schedule.csv")
        try:
            cars = [int(c) for c in a.cars.split(",") if c.strip()]
        except ValueError:
            sys.exit(f"--cars must be car ids like 299,350,351, got {a.cars!r}")
        if not 1 <= len(cars) <= 50 or len(set(cars)) != len(cars):
            sys.exit("--cars needs 1 to 50 different car ids")
        at, old = tier_cars(d, a.event)
        new = struct.pack("<I", len(cars)) + b"".join(struct.pack("<IB", c, 7 if i == 0 else 3)
                                                       for i, c in enumerate(cars))
        d[at:at + 4 + 5 * len(old)] = new
        _at, back = tier_cars(d, a.event)
        if [c for c, _f in back] != cars:
            sys.exit("internal error: cars did not read back")
        find_block(d)                          # the LTS block still parses
        save(a.out, d, encrypted, a.lib)
        print(f"{a.out}: event {a.event} cars {','.join(str(c) for c, _f in old)} -> "
              f"{','.join(str(c) for c in cars)}; file {len(new) - 4 - 5 * len(old):+d} bytes")
        return

    if a.cmd == "lts":
        lts = rr3_wtt.day_shift_for(a.lts_start, rr3_wtt.FIRST_LTS, rr3_wtt.CUTOFF_LTS, "--lts-start")
        rnd = rr3_wtt.day_shift_for(a.round_start, rr3_wtt.FIRST_ROUND, rr3_wtt.LAST_ROUND_END, "--round-start")
        moved = {"lts": 0, "round": 0}
        for r in recs:
            if (r["sub"] == 2 and r["wtt"]) or r["sub"] == 1 or r["end"] == 0 or r["end"] > rr3_wtt.CUTOFF_LTS:
                continue
            kind = "round" if r["sub"] == 0 and r["round"] else "lts"
            by = rnd if kind == "round" else lts
            s, e = r["start"] + by, r["end"] + by
            if a.lts_version == 2:
                s, e = tuesday_window(s, e)
            struct.pack_into("<II", d, r["at"], s, e)
            moved[kind] += 1
        save(a.out, d, encrypted, a.lib)
        print(f"{a.out}: {moved['lts']} plain LTS/TTC moved by {lts // 86400} days, "
              f"{moved['round']} Seasons LTS by {rnd // 86400} days"
              + (", then to Tuesdays 00:00 UTC in whole weeks" if a.lts_version == 2 else ""))
        return

    if a.cmd == "plan":
        build_plan(d, off, recs, a)
        save(a.out, d, encrypted, a.lib)
        return

    r = pick(recs, a)
    if a.cmd == "now":
        now = int(datetime.datetime.now(UTC).timestamp())
        start, end = now - 86400, now + int(a.days_left * 86400)
    else:
        start = parse_time(a.start)
        end = parse_time(a.end) if a.end else start + 7 * 86400
    if not start < end < 2 ** 31:
        sys.exit("start must be before end, and end before 2038-01-19")
    struct.pack_into("<II", d, r["at"], start, end)
    if parse_records(d, off)[recs.index(r)]["start"] != start:
        sys.exit("internal error: record did not read back")
    save(a.out, d, encrypted, a.lib)
    print(f"{a.out}: LTS index {r['key']}: {fmt(r['start'])} -> {fmt(r['end'])}  is now  "
          f"{fmt(start)} -> {fmt(end)} UTC (8 bytes at 0x{r['at']:x})")


if __name__ == "__main__":
    main()
