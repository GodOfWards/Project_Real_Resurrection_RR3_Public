#!/usr/bin/env python3
"""rr3_mp_traffic.py: traffic numbers from an rr3_mp_server.py log.

Part of Project Real Resurrection's work on Real Racing 3. Not affiliated
with, endorsed or supported by Electronic Arts.

Reads the server's stdout (one line per datagram, rr3_mp_server.py v0.3 and
later: time, port, direction, address, size, fmRUDP type, message) and
prints, for the whole log, each port, each phone, each room, each message
type and each race phase: datagrams and bytes in and out, the average per
second and the peak in one second. Issue #86 (traffic test, 2026-11-02).

Read-only: it only reads the log file(s) or stdin and prints. It never
talks to the server or touches its files, so it runs anywhere with a copy
of the log. Standard library only: install = copy this file, uninstall =
delete it.

Rooms are inferred: the server does not log room numbers, so phones that
get the same roster (LOBBY_SETTINGS / LOBBY_START_RACE with the same names)
within ROOM_GAP_S seconds of each other count as one room. Traffic before
a phone's first roster counts as "no room" (matchmaking, master server).

Usage:
  python3 rr3_mp_traffic.py mp.log
  python3 rr3_mp_traffic.py mp.log --from 20:15:00 --to 20:40:00
  python3 rr3_mp_traffic.py mp.log --csv traffic.csv
  some_command | python3 rr3_mp_traffic.py -

The output holds the phones' IP addresses: keep it off GitHub (issue #86,
privacy); only aggregated numbers go into analysis/mp-traffic.md.
"""
VERSION = "1.0"

import argparse
import csv
import re
import sys
from collections import defaultdict

# One datagram: "[0042] 20:15:03.123 :60001 <- 1.2.3.4:5555 42 bytes Data id ... [msg 12 GAME_POS_UPDATE]"
# (rr3_mp_server.py line()); any prefix (tee, journald) before it is skipped.
DATAGRAM_RE = re.compile(r"\[(\d{4,})\] (\d\d):(\d\d):(\d\d)\.(\d{3}) :(\d+) (<-|->) "
                         r"([0-9A-Fa-f.:]+):(\d+) (\d+) bytes (type \d+|\S+)(.*)$")
MSG_RE = re.compile(r"\[msg (\d+)(?: ([A-Z][A-Z0-9_]+))?")
INNER_RE = re.compile(r"from [0-9.]+:\d+: \[msg (\d+)(?: ([A-Z][A-Z0-9_]+))?")
ROSTER_RE = re.compile(r"\[msg (6|8) [A-Z_]+: flags \S+, you are slot \d+, (\d+) players (\[.*?\]), (\d+) slots")
# Server notes ("[----] ..." lines).
IGNORED_RE = re.compile(r"\[----\] ignored (\d+) datagram")
NOT_RELAYED_RE = re.compile(r"\[----\] not relayed: msg (\d+) of (\d+) bytes")
DENIED_RE = re.compile(r"\[----\] OMP (?:game port|master) denied build")
FAILED_RE = re.compile(r"\[----\] .* failed, dropped:")

MSG_START_RACE, MSG_FORWARD, MSG_COUNTDOWN, MSG_FINISHED, MSG_LEFT = 8, 55, 61, 14, 15
# Messages rr3_mp_server.py relays to the other phones of the room (RELAYED in v0.11-v0.18).
RELAYED = {7, 9, 10, 12, 14, 15, 35, 54, 57}
ROOM_GAP_S = 10.0           # rosters with the same names this close together are one room
DAY = 86400
PHASES = ["no room", "lobby", "loading", "race", "results"]


def clock(text):
    """'HH:MM:SS' (or with .mmm) as seconds after midnight."""
    m = re.fullmatch(r"(\d\d?):(\d\d):(\d\d)(?:\.(\d{1,3}))?", text)
    if not m:
        raise argparse.ArgumentTypeError(f"not a time HH:MM:SS: {text!r}")
    h, mi, s, ms = m.groups()
    return int(h) * 3600 + int(mi) * 60 + int(s) + int((ms or "0").ljust(3, "0")) / 1000


class Stats:
    """Datagrams and bytes in and out, with per-second buckets for the peaks."""

    def __init__(self):
        self.n = {"in": 0, "out": 0}
        self.b = {"in": 0, "out": 0}
        self.sec = defaultdict(lambda: [0, 0, 0, 0])   # second -> [n in, n out, bytes in, bytes out]
        self.first = self.last = None

    def add(self, t, way, size):
        self.n[way] += 1
        self.b[way] += size
        s = self.sec[int(t)]
        k = 0 if way == "in" else 1
        s[k] += 1
        s[k + 2] += size
        self.first = t if self.first is None else min(self.first, t)
        self.last = t if self.last is None else max(self.last, t)

    def row(self):
        span = max(1.0, (self.last - self.first) if self.first is not None else 0.0)
        peak = lambda i: max((v[i] for v in self.sec.values()), default=0)
        peak_n = max((v[0] + v[1] for v in self.sec.values()), default=0)
        return {"seconds": round(span, 1),
                "dgrams in": self.n["in"], "dgrams out": self.n["out"],
                "bytes in": self.b["in"], "bytes out": self.b["out"],
                "avg dgrams/s": round((self.n["in"] + self.n["out"]) / span, 1),
                "avg B/s in": round(self.b["in"] / span), "avg B/s out": round(self.b["out"] / span),
                "peak dgrams/s": peak_n, "peak B/s in": peak(2), "peak B/s out": peak(3)}


class Room:
    def __init__(self, rid, key, t):
        self.id, self.key, self.t = rid, key, t
        self.members, self.players = set(), 0
        self.started = self.countdown = None          # times of the first 8 and 61 sent
        self.done = set()                             # members that sent 14 or 15
        self.relay_in = self.relay_out = 0

    def phase(self, t):
        if self.countdown is not None and self.members and self.done >= self.members:
            return "results"
        if self.countdown is not None and t >= self.countdown:
            return "race"
        if self.started is not None and t >= self.started:
            return "loading"
        return "lobby"


class Traffic:
    def __init__(self, start=None, end=None):
        self.start, self.end = start, end
        self.total, self.ports, self.phones = Stats(), defaultdict(Stats), defaultdict(Stats)
        self.rooms_stats, self.msgs, self.phases = defaultdict(Stats), defaultdict(Stats), defaultdict(Stats)
        self.rooms, self.room_of = [], {}             # address -> Room
        self.day, self.prev, self.t0 = 0, None, None
        self.ignored = self.denied = self.failed = self.lines = self.other = 0
        self.not_relayed = set()

    def when(self, tod):
        """Time of day -> seconds on the log's own clock (a day added at each midnight)."""
        if self.prev is not None and tod < self.prev - DAY / 2:
            self.day += 1
        self.prev = tod
        return self.day * DAY + tod

    def in_range(self, t):
        return (self.start is None or t >= self.start) and (self.end is None or t <= self.end)

    def feed(self, raw):
        m = DATAGRAM_RE.search(raw)
        if not m:
            self.note(raw)
            return
        _, h, mi, s, ms, port, way, ip, cport, size, kind, rest = m.groups()
        t = self.when(int(h) * 3600 + int(mi) * 60 + int(s) + int(ms) / 1000)
        if not self.in_range(t):
            return
        self.lines += 1
        way = "in" if way == "<-" else "out"
        size, addr = int(size), f"{ip}:{cport}"
        msg, label = None, kind
        if kind == "Data":
            mm = MSG_RE.search(rest)
            if mm:
                msg = int(mm.group(1))
                label = f"Data {msg} {mm.group(2) or ''}".rstrip()
                if msg == MSG_FORWARD:
                    im = INNER_RE.search(rest)
                    if im:
                        label = f"Data 55 relay of {im.group(1)} {im.group(2) or ''}".rstrip()
        self.roster(t, way, addr, rest)
        room = self.room_of.get(addr)
        if room and way == "out" and msg == MSG_COUNTDOWN and room.countdown is None:
            room.countdown = t                            # the start messages open their phase,
        phase = room.phase(t) if room else "no room"      # a phone's own finish still counts in the race
        if room:
            self.track(room, t, way, addr, msg)
        for st in (self.total, self.ports[f":{port}"], self.phones[f"{addr} :{port}"], self.msgs[f"{way} {label}"],
                   self.rooms_stats[room.id if room else "no room"], self.phases[phase]):
            st.add(t, way, size)

    def roster(self, t, way, addr, rest):
        """A roster sent to a phone puts it in a room (see the module doc)."""
        m = ROSTER_RE.search(rest) if way == "out" else None
        if not m:
            return
        key = m.group(3)
        cur = self.room_of.get(addr)
        if cur and cur.key == key:
            room = cur
        else:
            room = next((r for r in reversed(self.rooms) if r.key == key and t - r.t <= ROOM_GAP_S), None)
            if room is None:
                room = Room(f"R{len(self.rooms) + 1}", key, t)
                self.rooms.append(room)
            if cur:
                cur.members.discard(addr)
            room.members.add(addr)
            self.room_of[addr] = room
        room.players = max(room.players, int(m.group(2)))
        if int(m.group(1)) == MSG_START_RACE and room.started is None:
            room.started = t

    def track(self, room, t, way, addr, msg):
        if way == "out" and msg == MSG_FORWARD:
            room.relay_out += 1
        if way == "in" and msg in RELAYED:
            room.relay_in += 1
        if way == "in" and msg in (MSG_FINISHED, MSG_LEFT) and room.countdown is not None:
            room.done.add(addr)

    def note(self, raw):
        for rx, what in ((IGNORED_RE, "ignored"), (NOT_RELAYED_RE, "not_relayed"),
                         (DENIED_RE, "denied"), (FAILED_RE, "failed")):
            m = rx.search(raw)
            if not m:
                continue
            if self.prev is not None and not self.in_range(self.day * DAY + self.prev):
                return
            if what == "ignored":
                self.ignored += int(m.group(1))
            elif what == "not_relayed":
                self.not_relayed.add((int(m.group(1)), int(m.group(2))))
            elif what == "denied":
                self.denied += 1
            else:
                self.failed += 1
            return
        if raw.strip():
            self.other += 1

    def tables(self):
        """[(section, name, row)] for printing and CSV."""
        out = [("total", "all", self.total.row())]
        out += [("port", k, v.row()) for k, v in sorted(self.ports.items())]
        rooms = {r.id: r for r in self.rooms}
        for k, v in sorted(self.rooms_stats.items(), key=lambda kv: (kv[0] != "no room", kv[0])):
            row = v.row()
            r = rooms.get(k)
            row["players"] = r.players if r else ""
            row["relay fan-out"] = round(r.relay_out / r.relay_in, 2) if r and r.relay_in else ""
            out.append(("room", k, row))
        for k, v in sorted(self.phones.items()):
            row = v.row()
            r = self.room_of.get(k.split(" ")[0])
            row["room"] = r.id if r else ""
            out.append(("phone", k, row))
        out += [("phase", k, self.phases[k].row()) for k in PHASES if k in self.phases]
        out += [("message", k, v.row()) for k, v in sorted(self.msgs.items(), key=lambda kv: -sum(kv[1].b.values()))]
        return out

    def notes(self):
        return [f"datagram lines read: {self.lines}; other lines skipped: {self.other}",
                f"ignored datagrams (no connection, summed by the server): {self.ignored}",
                f"builds denied: {self.denied}; server failures (datagram dropped): {self.failed}",
                "message kinds not relayed (each printed once by the server; drops over --relay-rate are "
                "not logged): " + (", ".join(f"msg {a} of {b} bytes" for a, b in sorted(self.not_relayed))
                                   or "none")]


COLUMNS = ["seconds", "dgrams in", "dgrams out", "bytes in", "bytes out", "avg dgrams/s",
           "avg B/s in", "avg B/s out", "peak dgrams/s", "peak B/s in", "peak B/s out"]
EXTRA = {"room": ["players", "relay fan-out"], "phone": ["room"]}


def print_tables(tr, f=sys.stdout):
    print(f"rr3_mp_traffic.py v{VERSION}", file=f)
    rows = tr.tables()
    for section in ["total", "port", "room", "phone", "phase", "message"]:
        part = [(n, r) for s, n, r in rows if s == section]
        if not part:
            continue
        cols = COLUMNS + EXTRA.get(section, [])
        head = [section] + cols
        cells = [[n] + [str(r.get(c, "")) for c in cols] for n, r in part]
        width = [max(len(x) for x in col) for col in zip(head, *cells)]
        print(file=f)
        for line in [head] + cells:
            print("  ".join(x.ljust(w) if i == 0 else x.rjust(w) for i, (x, w) in enumerate(zip(line, width))),
                  file=f)
    print(file=f)
    for n in tr.notes():
        print(n, file=f)


def write_csv(tr, path):
    cols = ["section", "name"] + COLUMNS + ["players", "relay fan-out", "room"]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for s, n, r in tr.tables():
            w.writerow([s, n] + [r.get(c, "") for c in cols[2:]])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Traffic numbers from an rr3_mp_server.py log (read-only).")
    ap.add_argument("logs", nargs="*", default=["-"], help="log file(s), in order; '-' or none = stdin")
    ap.add_argument("--from", dest="start", type=clock, help="first time to count, HH:MM:SS (log's first day)")
    ap.add_argument("--to", dest="end", type=clock, help="last time to count, HH:MM:SS (log's first day)")
    ap.add_argument("--csv", help="also write every table to this CSV file")
    ap.add_argument("--version", action="version", version=f"rr3_mp_traffic.py {VERSION}")
    a = ap.parse_args(argv)
    if a.start is not None and a.end is not None and a.end < a.start:
        a.end += DAY                                  # e.g. --from 23:50:00 --to 00:20:00
    tr = Traffic(a.start, a.end)
    for path in a.logs:
        f = sys.stdin if path == "-" else open(path, encoding="utf-8", errors="replace")
        try:
            for raw in f:
                tr.feed(raw.rstrip("\n"))
        finally:
            if f is not sys.stdin:
                f.close()
    if not tr.lines:
        print("No datagram lines found (is this an rr3_mp_server.py log?).", file=sys.stderr)
        return 1
    print_tables(tr)
    if a.csv:
        write_csv(tr, a.csv)
        print(f"CSV written to {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
