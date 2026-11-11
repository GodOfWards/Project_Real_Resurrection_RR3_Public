#!/usr/bin/env python3
"""List or move the Seasons rounds in data/championships.bin.nct (design #306
part B, research #287). v2 (#574, Tom 2026-11-09: every rotation on
Tuesday 00:00 UTC): rounds start and end on Tuesdays.

championships.bin is a FlatBuffers file (u32 root offset, file id `chmp`),
read by the static data loader 0x13dd2f0 into ChampionshipData
(analysis/championship-data.md section 3.2). Root field 0 = championships
(one per season); championship field 6 = rounds. A round has:

  f0 id (2021_ROUND_1)   f4 start (i64, Unix UTC)   f5 duration (s)
  f6 streams (series id + per-stream duration)      f9 a second date (i64)

EA's 39 rounds run 2021-01-06 to 2026-01-26, so no round is live today and
the Seasons LTS (plain LTS tied to a round) can't start. `shift` moves every
round's f4, and f9 when it is set, by the same whole number of days that
`rr3_wtt.py --round-start` uses for the Seasons LTS in events.dat (both map
2021_ROUND_1, 2021-01-06, to ROUND_START). Durations are kept, so the rounds
stay back to back. Only 8 bytes per date change; the file keeps its size.

f9 sits about 8 months after each round's end; it is probably the date the
round becomes "deprecated" (inferred, not traced). It is moved with the
round so it stays where it was relative to the round.

v2: after the shift, each round's start and end go to the nearest Tuesday
00:00 UTC (rr3_wtt_dates.py v7's rule), so the rounds stay back to back
and last whole weeks; f5 (duration) is rewritten and f9 moves with the
start. The round streams' own durations (7 days for a Seasons LTS, a
personal timer from when the player starts it) are kept. --version 1
writes v1's exact shift.

  rr3_championships.py list IN
  rr3_championships.py shift IN OUT [--round-start YYYY-MM-DD] [--version 1]

IN and OUT are encrypted .nct files (as on the phone); a decrypted file
(starting with the `chmp` header) is also accepted and written back
decrypted. The key comes from the develified lib (--lib). The OUT file is
for our CDN (design #306 B); keep the original.
"""
import argparse
import datetime
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rr3_nct  # noqa: E402
import rr3_wtt  # noqa: E402  (the same anchor and default as the lib patch)
import rr3_wtt_dates  # noqa: E402  (v2: the Tuesday rule, #574)

VERSION = "2"
LIB = os.path.join(HERE, "..", "game", "develified-libRealRacing3.so.gz")
FILE_ID = b"chmp"
UTC = datetime.timezone.utc
FIRST_ROUND = rr3_wtt.FIRST_ROUND                 # 2021-01-06, 2021_ROUND_1
LAST_ROUND_END = rr3_wtt.LAST_ROUND_END           # 2026-01-26 20:00, end of 2025_ROUND_03
DEFAULT_START = rr3_wtt.DEFAULT_START
F_ID, F_START, F_DURATION, F_STREAMS, F_DATE2 = 0, 4, 5, 6, 9


class Bad(Exception):
    pass


class Fb:
    """Just enough FlatBuffers to walk championships.bin."""

    def __init__(self, d):
        self.d = d

    def u32(self, o):
        if not 0 <= o <= len(self.d) - 4:
            raise Bad(f"offset 0x{o:x} outside the file")
        return struct.unpack_from("<I", self.d, o)[0]

    def fields(self, t):
        vt = t - struct.unpack_from("<i", self.d, t)[0]
        n = (struct.unpack_from("<H", self.d, vt)[0] - 4) // 2
        if not 0 <= vt < len(self.d) or n > 64:
            raise Bad(f"bad vtable for table 0x{t:x}")
        return [t + o if o else None for o in struct.unpack_from(f"<{n}H", self.d, vt + 4)]

    def ref(self, o):
        return o + self.u32(o)

    def vec(self, o):
        v = self.ref(o)
        return [v + 4 + 4 * k for k in range(self.u32(v))]

    def string(self, o):
        v = self.ref(o)
        return self.d[v + 4:v + 4 + self.u32(v)].decode("latin1")

    def i64(self, o):
        return struct.unpack_from("<q", self.d, o)[0]

    def i32(self, o):
        return struct.unpack_from("<i", self.d, o)[0]


def rounds(d):
    """Every round: dict(season, id, start, duration, streams, start_at, date2, date2_at)."""
    if bytes(d[4:8]) != FILE_ID:
        raise Bad("not championships.bin (no `chmp` file id)")
    fb = Fb(d)
    out = []
    root = fb.fields(fb.u32(0))
    for c in fb.vec(root[0]):
        cf = fb.fields(fb.ref(c))
        season = fb.string(cf[F_ID])
        if len(cf) <= 6 or cf[6] is None:
            continue
        for r in fb.vec(cf[6]):
            rf = fb.fields(fb.ref(r)) + [None] * 10
            if rf[F_START] is None:
                raise Bad(f"round in {season} without a start")
            out.append({
                "season": season, "id": fb.string(rf[F_ID]),
                "start": fb.i64(rf[F_START]), "start_at": rf[F_START],
                "duration": fb.i32(rf[F_DURATION]) if rf[F_DURATION] else 0, "duration_at": rf[F_DURATION],
                "streams": len(fb.vec(rf[F_STREAMS])) if rf[F_STREAMS] else 0,
                "date2": fb.i64(rf[F_DATE2]) if rf[F_DATE2] else 0, "date2_at": rf[F_DATE2],
            })
    if not out:
        raise Bad("no rounds")
    return out


def load(path, lib):
    raw = open(path, "rb").read()
    if raw[4:8] == FILE_ID:
        return bytearray(raw), False
    d = bytearray(rr3_nct.crypt(raw, rr3_nct.read_lib(lib)))
    if d[4:8] != FILE_ID:
        sys.exit(f"{path}: not championships.bin (no `chmp` after decrypting)")
    return d, True


def save(path, d, encrypted, lib):
    open(path, "wb").write(rr3_nct.crypt(bytes(d), rr3_nct.read_lib(lib)) if encrypted else bytes(d))


def fmt(t):
    return datetime.datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%d %H:%M") if t else "-"


def shift_for(start):
    """Whole-day shift mapping 2021_ROUND_1 (2021-01-06) to `start`; the same
    rule as rr3_wtt.py --round-start."""
    try:
        d = datetime.datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        sys.exit(f"--round-start must be YYYY-MM-DD, got {start!r}")
    if int(d.timestamp()) <= LAST_ROUND_END:
        sys.exit(f"--round-start must be after EA's last round end (2026-01-26), got {start}")
    return int((d - FIRST_ROUND).total_seconds())


def shift(d, by, version=2):
    """Move every round start, and f9 when set, by `by` seconds (in place);
    v2 then puts each start and end on the nearest Tuesday 00:00 UTC."""
    rs = rounds(d)
    if any(r["start"] > LAST_ROUND_END for r in rs):
        sys.exit("this file already has rounds after EA's last one: shift the original instead")
    last = 0
    for r in rs:
        s, e = r["start"] + by, r["start"] + r["duration"] + by
        if version == 2:
            if r["duration_at"] is None:
                raise Bad(f"round {r['id']} has no duration field to rewrite")
            s, e = rr3_wtt_dates.tuesday_window(s, e)
            struct.pack_into("<i", d, r["duration_at"], e - s)
        struct.pack_into("<q", d, r["start_at"], s)
        if r["date2_at"] is not None and r["date2"]:
            struct.pack_into("<q", d, r["date2_at"], r["date2"] + (s - r["start"]))
        last = max(last, e, r["date2"] + (s - r["start"]) if r["date2"] else 0)
    if last >= 2 ** 31:
        sys.exit("the moved rounds would pass 2038-01-19 (32-bit times)")
    return len(rs)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lib", default=LIB, help="develified lib, for the .nct key")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list")
    ls.add_argument("inp")
    sh = sub.add_parser("shift")
    sh.add_argument("inp")
    sh.add_argument("out")
    sh.add_argument("--round-start", default=DEFAULT_START,
                    help=f"day 2021_ROUND_1 moves to; must match rr3_wtt.py --round-start (default {DEFAULT_START})")
    sh.add_argument("--version", type=int, choices=(1, 2), default=2,
                    help="2 (default): rounds on Tuesdays 00:00 UTC in whole weeks (#574); 1: exact shift")
    a = ap.parse_args()

    d, enc = load(a.inp, a.lib)
    try:
        if a.cmd == "list":
            for r in rounds(d):
                print(f"{r['season']:18} {r['id']:22} {fmt(r['start'])} -> {fmt(r['start'] + r['duration'])}"
                      f"  {r['duration'] // 86400:3d} d  {r['streams']:2d} streams  f9 {fmt(r['date2'])}")
            return
        by = shift_for(a.round_start)
        n = shift(d, by, a.version)
    except Bad as e:
        sys.exit(f"{a.inp}: {e}")
    save(a.out, d, enc, a.lib)
    first = min(r["start"] for r in rounds(d))
    print(f"{a.out}: {n} rounds moved by {by // 86400} days; first round starts {fmt(first)}")


if __name__ == "__main__":
    main()
