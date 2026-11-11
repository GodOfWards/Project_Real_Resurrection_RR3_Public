#!/usr/bin/env python3
"""List or re-date the Featured quests in data/jobs.bin.nct (design #306
part C, research #38). v2 (#574, Tom 2026-11-09: every rotation on
Tuesday 00:00 UTC): whole-week lengths, every group on a Tuesday.

jobs.bin holds 182 quests (JobReader 0x1170d74; quest section read by
0xf957cc, record reader 0xf84c98; analysis/limited-time-series.md §4b,
§6.5, §6.8). Per quest, after the id, a u32 and the career type string,
five u32 follow; the last three are

  field 7  lead (s)   shown this long before the start   (quest +0x2b0)
  field 8  start      Unix UTC                            (quest +0x2a0)
  field 9  end        Unix UTC, 0 = none                  (quest +0x2a8)

and the game adds a quest time offset (0 normally). The 1069 quest stages
carry no times (all 0), so a Featured quest's window is only fields 8/9.
EA's 14 Featured quests are all in the past or undated, so none shows.

`schedule` writes the decided plan (Tom, 2026-11-04; v2 2026-11-09):
EA's order and groups, the first group on FIRST (default Tue 2026-12-01
00:00 UTC), then one group every two weeks; a group that runs longer than
two weeks pushes the next one to its end, so no two Featured quests
overlap. v2: each length is EA's rounded to whole weeks, at least one
(undated ones 7 days), and FIRST must be a Tuesday, so every start and end
is a Tuesday 00:00 UTC. v1 (--version 1) kept EA's lengths and pushed a
later group to the day after the longer one ended. Lead times stay as EA's.

  group  quests                                         EA length      v2
  1      NASCAR_Penske, _Gibbs, _Stewart, _Hendrick     (undated) 7 d  1 week
  2      DAYTONA_Penske, _Gibbs, _Stewart, _Hendrick    16 d 5 h       2 weeks
  3      JaguarLegacy_EType                             5 d 4 h        1 week
  4      Bathurst2016Holden, Bathurst2016Ford           9 d            1 week
  5      Daytona2017                                    (undated) 7 d  1 week
  6      Fearless                                       5 d            1 week
  7      TDVirtual                                      (undated) 7 d  1 week

Only fields 8 and 9 of those 14 quests change (8 bytes each); the file
keeps its size.

  rr3_quests.py list IN [--all]
  rr3_quests.py schedule IN OUT [--first YYYY-MM-DD] [--version 1]
  rr3_quests.py set IN OUT QUEST_ID --start "YYYY-MM-DD HH:MM" [--end ...]

IN and OUT are encrypted .nct files (as on the phone); a decrypted file is
also accepted and written back decrypted (recognised by its quest section).
The key comes from the develified lib (--lib). The OUT file is for our CDN;
keep the original.
"""
import argparse
import datetime
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rr3_nct  # noqa: E402

VERSION = "2"
LIB = os.path.join(HERE, "..", "game", "develified-libRealRacing3.so.gz")
UTC = datetime.timezone.utc
KNOWN_OFFSET = 0x34A3D3          # quest section in Tom's file, md5 857b634fa8bba36e97d97d40e23db948
QUESTS = 182
TYPES = (b"Featured", b"Flashback", b"Career", b"CareerDeprecated")
DAY = 86400
DEFAULT_FIRST = "2026-12-01"
GROUPS = [
    ["NASCAR_Penske", "NASCAR_Gibbs", "NASCAR_Stewart", "NASCAR_Hendrick"],
    ["DAYTONA_Penske", "DAYTONA_Gibbs", "DAYTONA_Stewart", "DAYTONA_Hendrick"],
    ["JaguarLegacy_EType"],
    ["Bathurst2016Holden", "Bathurst2016Ford"],
    ["Daytona2017"],
    ["Fearless"],
    ["TDVirtual"],
]
UNDATED_LENGTH = 7 * DAY
EVERY = 14 * DAY
WEEK = 7 * DAY


class Bad(Exception):
    pass


def u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


def record_at(d, p):
    """(id, career type, offset of field 5) if a quest record starts at p, else None."""
    if p + 8 > len(d):
        return None
    n = u32(d, p + 4)
    if not 0 < n < 80 or not re.fullmatch(rb"[\x21-\x7e]+", d[p + 8:p + 8 + n]):
        return None
    q = p + 8 + n + 4
    if q + 4 > len(d):
        return None
    tl = u32(d, q)
    ct = bytes(d[q + 4:q + 4 + tl])
    if ct not in TYPES:
        return None
    return d[p + 8:p + 8 + n].decode(), ct.decode(), q + 4 + tl


def quests(d):
    """The 182 quests: dict(index, id, type, lead, start, end, at) with `at` the
    file offset of field 7."""
    if len(d) < KNOWN_OFFSET + 4 or u32(d, KNOWN_OFFSET) != QUESTS:
        raise Bad(f"no quest section ({QUESTS} quests) at 0x{KNOWN_OFFSET:x}")
    out, p = [], KNOWN_OFFSET + 4
    for i in range(QUESTS):
        while True:
            if p >= len(d) - 8:
                raise Bad(f"quest {i} not found")
            r = record_at(d, p)
            if r:
                break
            p += 1
        qid, ct, f5 = r
        lead, start, end = struct.unpack_from("<3I", d, f5 + 8)
        out.append({"index": i, "id": qid, "type": ct, "lead": lead, "start": start, "end": end, "at": f5 + 8})
        p = f5 + 20
    return out


def load(path, lib):
    raw = open(path, "rb").read()
    try:
        quests(raw)
        return bytearray(raw), False
    except (Bad, struct.error):
        pass
    d = bytearray(rr3_nct.crypt(raw, rr3_nct.read_lib(lib)))
    try:
        quests(d)
    except (Bad, struct.error) as e:
        sys.exit(f"{path}: not jobs.bin ({e})")
    return d, True


def save(path, d, encrypted, lib):
    open(path, "wb").write(rr3_nct.crypt(bytes(d), rr3_nct.read_lib(lib)) if encrypted else bytes(d))


def fmt(t):
    return datetime.datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%d %H:%M") if t else "-"


def parse_day(s, what):
    try:
        return int(datetime.datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())
    except ValueError:
        sys.exit(f"{what} must be YYYY-MM-DD, got {s!r}")


def parse_time(s, what):
    try:
        return int(datetime.datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=UTC).timestamp())
    except ValueError:
        sys.exit(f"{what} must be 'YYYY-MM-DD HH:MM' (UTC), got {s!r}")


def weeks(length):
    """v2: a length rounded to whole weeks, at least one (half a week rounds up)."""
    return max(1, (length + WEEK // 2) // WEEK) * WEEK


def plan(qs, first, version=2):
    """[(quest id, start, end)] for GROUPS from `first` (Unix, 00:00 UTC;
    v2: a Tuesday)."""
    if version == 2 and datetime.datetime.fromtimestamp(first, UTC).weekday() != 1:
        raise Bad(f"--first must be a Tuesday (v2, #574), {fmt(first)[:10]} is not")
    by = {q["id"]: q for q in qs}
    out, start = [], first
    for g in GROUPS:
        missing = [x for x in g if x not in by]
        if missing:
            raise Bad(f"Featured quest(s) not in this file: {', '.join(missing)}")
        q0 = by[g[0]]
        length = q0["end"] - q0["start"] if q0["start"] and q0["end"] else UNDATED_LENGTH
        if version == 2:
            length = weeks(length)
        end = start + length
        out += [(x, start, end) for x in g]
        start = max(start + EVERY, (end + DAY - 1) // DAY * DAY)       # no overlap
    if out[-1][2] >= 2 ** 31:
        raise Bad("the plan passes 2038-01-19 (32-bit times)")
    return out


def write(d, qs, qid, start, end):
    q = next((q for q in qs if q["id"] == qid), None)
    if q is None:
        sys.exit(f"no quest {qid!r} in this file")
    if not 0 < start < end < 2 ** 31:
        sys.exit(f"{qid}: start must be before end, both before 2038")
    struct.pack_into("<2I", d, q["at"] + 4, start, end)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lib", default=LIB, help="develified lib, for the .nct key")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list")
    ls.add_argument("inp")
    ls.add_argument("--all", action="store_true", help="every quest, not only Featured")
    sc = sub.add_parser("schedule")
    sc.add_argument("inp")
    sc.add_argument("out")
    sc.add_argument("--first", default=DEFAULT_FIRST,
                    help=f"day the first group starts, 00:00 UTC; a Tuesday in v2 (default {DEFAULT_FIRST})")
    sc.add_argument("--version", type=int, choices=(1, 2), default=2,
                    help="2 (default): whole weeks from Tuesdays (#574); 1: EA's lengths")
    st = sub.add_parser("set")
    st.add_argument("inp")
    st.add_argument("out")
    st.add_argument("quest")
    st.add_argument("--start", required=True, help="'YYYY-MM-DD HH:MM' UTC")
    st.add_argument("--end", help="'YYYY-MM-DD HH:MM' UTC (default start + 7 days)")
    a = ap.parse_args()

    d, enc = load(a.inp, a.lib)
    qs = quests(d)
    if a.cmd == "list":
        for q in qs:
            if a.all or q["type"] == "Featured":
                print(f"{q['index']:3d}  {q['id']:40} {q['type']:16} {fmt(q['start'])} -> {fmt(q['end'])}"
                      f"  lead {q['lead'] // DAY} d")
        return
    if a.cmd == "schedule":
        try:
            p = plan(qs, parse_day(a.first, "--first"), a.version)
        except Bad as e:
            sys.exit(f"{a.inp}: {e}")
        for qid, s, e in p:
            write(d, qs, qid, s, e)
            print(f"{qid:22} {fmt(s)} -> {fmt(e)}")
    else:
        s = parse_time(a.start, "--start")
        e = parse_time(a.end, "--end") if a.end else s + 7 * DAY
        write(d, qs, a.quest, s, e)
        print(f"{a.quest}: {fmt(s)} -> {fmt(e)}")
    save(a.out, d, enc, a.lib)
    print(f"{a.out}: written")


if __name__ == "__main__":
    main()
