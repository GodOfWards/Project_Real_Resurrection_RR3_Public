#!/usr/bin/env python3
"""Bring back EA's limited-time series offline: replay the Weekly Time Trials,
the plain LTS, the Time Trial Competitions and the Seasons LTS from new
start dates, in libRealRacing3.so (v14.0.1, arm64, develified build).
v1: issue #194 (design #191), WTTs only. v2: design #306 (research #38).
Guides: docs/weekly-time-trial.md, docs/limited-time-series.md.

data/events.dat.nct holds 805 LTS records (analysis/lts-schedule.csv), all
in the past, so none shows. The patch moves them forward by a constant
while the records are loaded, so the game sees the new dates everywhere
(live check, "ends in" timer, candidate list). Order, lengths and overlaps
stay as EA ran them.

Hook in the LTS parser (0xc32f70), at 0xc33358 `sub x19, x24, x21` (the
lead time). Every field of the record has been read there: w28 = sub type,
[sp+0xa4] = WTT flag (+0x70), x24 = start, [sp+0x90] = end, x21 = lead,
and field 17 (the championship round, rec +0xc0) is the std::string at
[x29-0xd0]. Both store paths (0xc33368, 0xc33510) come after it.

v2 (`wtt@v2`): 0xc33358 -> bl 0x1584450. Three shifts:

  record                                   shift       maps          to
  sub type 2 + WTT flag (384 WTTs)         SHIFT_WTT   2018-08-21    --start
  sub type 0 with a round (Seasons LTS)    SHIFT_ROUND 2021-01-06    --round-start
  other sub type 0 and 2 (plain LTS, TTC)  SHIFT_LTS   2016-03-10    --lts-start

Not moved: sub type 1 (the community LTS), end = 0 (the F1 2023 team
group, "always live"), and records that end after EA's last one (WTT
2025-12-15 20:00, others 2025-12-21 00:00 UTC): those come from our own
events.dat and are used as written. The Seasons rounds themselves are in
data/championships.bin, moved by the same SHIFT_ROUND in a served file
(design #306 B). Cave 0x1584450 (unreferenced debug function,
tables/lib-code-caves.csv), 33 instructions:

  cmp  w28, #1 ; b.eq out            community LTS: keep
  ldr  x9, [sp, #0x90] ; cbz x9, out end 0 (F1 2023 group): keep
  cmp  w28, #2 ; b.ne sub0
  ldr  w8, [sp, #0xa4] ; cbz w8, lts TTC without the WTT flag: LTS shift
  mov  x10, #SHIFT_WTT ; mov x8, #CUTOFF_WTT ; b apply
sub0:
  ldurb w8, [x29, #-0xd0]            libc++ string: bit 0 = long form
  tbz  w8, #0, short ; ldur x8, [x29, #-0xc8] ; b chk
short: lsr w8, w8, #1                short form: size in byte 0 >> 1
chk: cbz x8, lts
  mov  x10, #SHIFT_ROUND ; b cut
lts: mov x10, #SHIFT_LTS
cut: mov x8, #CUTOFF_LTS
apply:
  cmp  x9, x8 ; b.gt out             later records: ours, keep
  add  x24, x24, x10 ; add x9, x9, x10 ; str x9, [sp, #0x90]
out: sub x19, x24, x21               the replaced instruction
  ret

x8, x9, x10 are free there (x8/x9 reloaded at 0xc3335c, x10 written
before it is read on both paths).

v1 (`wtt`, `--version 1`): 0xc33358 -> bl 0x1b4ff08, WTTs only (64 bytes
in the zero padding at 0x1b4ff08). `check` still recognises it.

Defaults (Tom, 2026-11-03 and 2026-11-04): all three start Tue 2026-11-17
00:00 UTC. SHIFT_WTT = 430 weeks; SHIFT_LTS = 3904 days (0x141ae000);
SHIFT_ROUND = 2141 days (0xb069b80). Shifted times must stay below 2^31.

Usage:
  rr3_wtt.py check LIB
  rr3_wtt.py patch IN OUT [--start YYYY-MM-DD] [--lts-start YYYY-MM-DD] [--round-start YYYY-MM-DD]
  rr3_wtt.py patch IN OUT --version 1 [--start YYYY-MM-DD]
  rr3_wtt.py patch IN OUT --restore
IN may be gzipped; OUT is written uncompressed (or gzipped if it ends in .gz).
A patched lib can be patched again with another --start.
"""
import argparse
import datetime
import gzip
import struct
import sys

SITE = 0xC33358
SITE_DEVELIFIED = 0xCB150313          # sub x19, x24, x21
CAVE = 0x1B4FF08                      # v1
CAVE_END = 0x1B4FF80                  # the cave's end (120 bytes); v1 uses 64
CAVE2 = 0x1584450                     # v2: free part of the unreferenced debug function 0x1583704
CAVE2_END = 0x15846A8
REQUIRES = []                         # neither cave needs anything switched off first
VERSION = 2

UTC = datetime.timezone.utc
FIRST = datetime.datetime(2018, 8, 21, tzinfo=UTC)          # EA's first WTT week
FIRST_LTS = datetime.datetime(2016, 3, 10, tzinfo=UTC)      # EA's first LTS (plain)
FIRST_ROUND = datetime.datetime(2021, 1, 6, tzinfo=UTC)     # 2021_ROUND_1, the first Seasons round
CUTOFF = 1765828800                   # 2025-12-15 20:00 UTC, end of EA's last WTT
LAST_END = CUTOFF
CUTOFF_LTS = 1766275200               # 2025-12-21 00:00 UTC, end of EA's last other LTS
LAST_ROUND_END = 1769457600           # 2026-01-26 20:00 UTC, end of 2025_ROUND_03 (championships.bin)
DEFAULT_START = "2026-11-17"
WEEK = 7 * 86400
DAY = 86400


def movz(rd, imm16, hw=0):
    return 0xD2800000 | (hw << 21) | (imm16 << 5) | rd


def movk(rd, imm16, hw):
    return 0xF2800000 | (hw << 21) | (imm16 << 5) | rd


def bcond(at, to, cond):
    return 0x54000000 | ((((to - at) >> 2) & 0x7FFFF) << 5) | cond


def cbz_w(at, to, rt):
    return 0x34000000 | ((((to - at) >> 2) & 0x7FFFF) << 5) | rt


def cbz_x(at, to, rt):
    return 0xB4000000 | ((((to - at) >> 2) & 0x7FFFF) << 5) | rt


def tbz(at, to, rt, bit):
    return 0x36000000 | (bit << 19) | ((((to - at) >> 2) & 0x3FFF) << 5) | rt


def b(at, to):
    return 0x14000000 | (((to - at) >> 2) & 0x3FFFFFF)


def bl(at, to):
    return 0x94000000 | (((to - at) >> 2) & 0x3FFFFFF)


def mov32(rd, v):
    return [movz(rd, v & 0xFFFF), movk(rd, v >> 16, 1)]


def cave_words(shift):
    """v1: the 16 cave instructions for a SHIFT in seconds (WTTs only)."""
    a = lambda i: CAVE + 4 * i                                   # noqa: E731
    out = 14                                                     # index of the replaced sub
    return [
        0x71000B9F,                                              # cmp w28, #2
        bcond(a(1), a(out), 0x1),                                # b.ne 1f
        0xB940A7E8,                                              # ldr w8, [sp, #0xa4]
        cbz_w(a(3), a(out), 8),                                  # cbz w8, 1f
        0xF9404BE9,                                              # ldr x9, [sp, #0x90]
        movz(8, CUTOFF & 0xFFFF),                                # mov x8, #CUTOFF
        movk(8, CUTOFF >> 16, 1),
        0xEB08013F,                                              # cmp x9, x8
        bcond(a(8), a(out), 0xC),                                # b.gt 1f
        movz(8, shift & 0xFFFF),                                 # mov x8, #SHIFT
        movk(8, shift >> 16, 1),
        0x8B080318,                                              # add x24, x24, x8
        0x8B080129,                                              # add x9, x9, x8
        0xF9004BE9,                                              # str x9, [sp, #0x90]
        SITE_DEVELIFIED,                                         # sub x19, x24, x21
        0xD65F03C0,                                              # ret
    ]


CAVE_LEN = 4 * len(cave_words(0))

# v2 labels (instruction indexes)
SUB0, SHORT, CHK, LTS, CUT, APPLY, OUT = 13, 17, 18, 22, 24, 26, 31


def cave2_words(wtt, lts, rnd):
    """v2: the 33 cave instructions for the three shifts in seconds."""
    a = lambda i: CAVE2 + 4 * i                                  # noqa: E731
    w = [
        0x7100079F,                                              # 0  cmp w28, #1
        bcond(a(1), a(OUT), 0x0),                                # 1  b.eq out
        0xF9404BE9,                                              # 2  ldr x9, [sp, #0x90]
        cbz_x(a(3), a(OUT), 9),                                  # 3  cbz x9, out
        0x71000B9F,                                              # 4  cmp w28, #2
        bcond(a(5), a(SUB0), 0x1),                               # 5  b.ne sub0
        0xB940A7E8,                                              # 6  ldr w8, [sp, #0xa4]
        cbz_w(a(7), a(LTS), 8),                                  # 7  cbz w8, lts
        *mov32(10, wtt),                                         # 8  mov x10, #SHIFT_WTT
        *mov32(8, CUTOFF),                                       # 10 mov x8, #CUTOFF_WTT
        b(a(12), a(APPLY)),                                      # 12 b apply
        0x385303A8,                                              # 13 sub0: ldurb w8, [x29, #-0xd0]
        tbz(a(14), a(SHORT), 8, 0),                              # 14 tbz w8, #0, short
        0xF85383A8,                                              # 15 ldur x8, [x29, #-0xc8]
        b(a(16), a(CHK)),                                        # 16 b chk
        0x53017D08,                                              # 17 short: lsr w8, w8, #1
        cbz_x(a(CHK), a(LTS), 8),                                # 18 chk: cbz x8, lts
        *mov32(10, rnd),                                         # 19 mov x10, #SHIFT_ROUND
        b(a(21), a(CUT)),                                        # 21 b cut
        *mov32(10, lts),                                         # 22 lts: mov x10, #SHIFT_LTS
        *mov32(8, CUTOFF_LTS),                                   # 24 cut: mov x8, #CUTOFF_LTS
        0xEB08013F,                                              # 26 apply: cmp x9, x8
        bcond(a(27), a(OUT), 0xC),                               # 27 b.gt out
        0x8B0A0318,                                              # 28 add x24, x24, x10
        0x8B0A0129,                                              # 29 add x9, x9, x10
        0xF9004BE9,                                              # 30 str x9, [sp, #0x90]
        SITE_DEVELIFIED,                                         # 31 out: sub x19, x24, x21
        0xD65F03C0,                                              # 32 ret
    ]
    assert len(w) == 33
    return w


CAVE2_LEN = 4 * len(cave2_words(0, 0, 0))
# The dead physics-state compare's words in the slice 0x1584450..0x15844d4 (v2 cave).
CAVE2_DEVELIFIED = (
    0x3707BE80, 0x90FF7140, 0x9115F400, 0x97EC6D6F, 0x2A1F03F5, 0xB94EAE88,
    0xB94EAE69, 0x6B09011F, 0x54FFBE00, 0xF0FF7560, 0x9130B000, 0x97EC6D67,
    0x2A1F03F5, 0xB94EB688, 0xB94EB669, 0x6B09011F, 0x54FFBD80, 0xB0FF7320,
    0x91054C00, 0x97EC6D5F, 0x2A1F03F5, 0xB94EBA88, 0xB94EBA69, 0x6B09011F,
    0x54FFBD00, 0xD0FF74A0, 0x910F8800, 0x97EC6D57, 0x2A1F03F5, 0xB94EBE88,
    0xB94EBE69, 0x6B09011F, 0x54FFBC80,
)
CAVE2_DEV = struct.pack("<33I", *CAVE2_DEVELIFIED)


def load(path):
    data = open(path, "rb").read()
    return bytearray(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def parse_date(s, what):
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        sys.exit(f"{what} must be YYYY-MM-DD, got {s!r}")


def shift_for(start):
    """SHIFT_WTT in seconds for a start date 'YYYY-MM-DD'; exits on a bad date."""
    d = parse_date(start, "--start")
    if d.weekday() != 1:
        sys.exit(f"--start must be a Tuesday (EA's changeover day), {start} is a {d:%A}")
    shift = int((d - FIRST).total_seconds())
    if shift <= LAST_END - int(FIRST.timestamp()):
        sys.exit(f"--start must be after EA's last WTT (2025-12-15), got {start}")
    if LAST_END + shift >= 2 ** 31:
        sys.exit(f"--start {start} pushes the last week past 2038-01-19 (32-bit times)")
    return shift


def day_shift_for(start, first, last_end, what):
    """Whole-day shift mapping `first` to `start`; the moved records must start
    after `last_end` (EA's last) and end before 2^31."""
    d = parse_date(start, what)
    shift = int((d - first).total_seconds())
    if int(d.timestamp()) <= last_end:
        sys.exit(f"{what} must be after EA's last one "
                 f"({datetime.datetime.fromtimestamp(last_end, UTC):%Y-%m-%d}), got {start}")
    if CUTOFF_LTS + shift >= 2 ** 31:
        sys.exit(f"{what} {start} pushes the last series past 2038-01-19 (32-bit times)")
    return shift


def start_for(shift, first=FIRST):
    return (first + datetime.timedelta(seconds=shift)).strftime("%Y-%m-%d")


def imm32(words, k):
    return ((words[k + 1] >> 5) & 0xFFFF) << 16 | ((words[k] >> 5) & 0xFFFF)


def patched(d):
    """None develified, (1, wtt) or (2, wtt, lts, round) if patched, False unrecognised."""
    site = struct.unpack_from("<I", d, SITE)[0]
    cave = bytes(d[CAVE:CAVE + CAVE_LEN])
    cave2 = bytes(d[CAVE2:CAVE2 + CAVE2_LEN])
    if site == SITE_DEVELIFIED and cave == b"\0" * CAVE_LEN and cave2 == CAVE2_DEV:
        return None
    if site == bl(SITE, CAVE) and cave2 == CAVE2_DEV:
        words = list(struct.unpack("<%dI" % (CAVE_LEN // 4), cave))
        shift = imm32(words, 9)
        if words == cave_words(shift) and not shift % WEEK:
            return (1, shift)
        return False
    if site == bl(SITE, CAVE2) and cave == b"\0" * CAVE_LEN:
        words = list(struct.unpack("<%dI" % (CAVE2_LEN // 4), cave2))
        wtt, rnd, lts = imm32(words, 8), imm32(words, 19), imm32(words, 22)
        if words == cave2_words(wtt, lts, rnd) and not wtt % WEEK and not lts % DAY and not rnd % DAY:
            return (2, wtt, lts, rnd)
    return False


def shift_in(d):
    """v1 compatible: None develified, SHIFT_WTT if patched, False unrecognised."""
    p = patched(d)
    return p if p in (None, False) else p[1]


def contents(d):
    """`patches` entry for rr3_build.py: '' develified, None unrecognised.
    v1: wtt=2026-11-17 (the start of WTT week 1); v2:
    wtt@v2=2026-11-17+lts=2026-11-17+rounds=2026-11-17."""
    p = patched(d)
    if p is False:
        return None
    if p is None:
        return ""
    if p[0] == 1:
        return f"wtt={start_for(p[1])}"
    return (f"wtt@v2={start_for(p[1])}+lts={start_for(p[2], FIRST_LTS)}"
            f"+rounds={start_for(p[3], FIRST_ROUND)}")


def state(d):
    p = patched(d)
    if p is False:
        return None
    if p is None:
        return "develified (all LTS on EA's dates, all in the past)"
    if p[0] == 1:
        return f"patched v1 (WTT week 1 on {start_for(p[1])}, shift {p[1] // WEEK} weeks; other LTS unchanged)"
    return (f"patched v2 (WTT week 1 on {start_for(p[1])}, shift {p[1] // WEEK} weeks; "
            f"plain LTS and TTC from {start_for(p[2], FIRST_LTS)}, shift {p[2] // DAY} days; "
            f"Seasons LTS from {start_for(p[3], FIRST_ROUND)}, shift {p[3] // DAY} days)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("lib")
    p = sub.add_parser("patch")
    p.add_argument("inp")
    p.add_argument("out")
    p.add_argument("--start", default=DEFAULT_START,
                   help=f"Tuesday when WTT week 1 starts, 00:00 UTC (default {DEFAULT_START})")
    p.add_argument("--lts-start", default=DEFAULT_START,
                   help=f"day EA's first plain LTS (2016-03-10) moves to (default {DEFAULT_START})")
    p.add_argument("--round-start", default=DEFAULT_START,
                   help=f"day 2021_ROUND_1 (2021-01-06) moves to; must match the served "
                        f"championships.bin (default {DEFAULT_START})")
    p.add_argument("--version", type=int, choices=(1, 2), default=VERSION,
                   help="1: WTTs only (old cave 0x1b4ff08); 2 (default): WTT, plain LTS, TTC, Seasons")
    p.add_argument("--restore", action="store_true", help="put the develified bytes back")
    a = ap.parse_args()

    d = load(a.lib if a.cmd == "check" else a.inp)
    if state(d) is None:
        sys.exit("unexpected bytes at 0xc33358, 0x1b4ff08 or 0x1584450: not the v14.0.1 develified build?")
    if a.cmd == "check":
        print(state(d))
        return
    struct.pack_into("<I", d, SITE, SITE_DEVELIFIED)
    d[CAVE:CAVE + CAVE_LEN] = b"\0" * CAVE_LEN
    d[CAVE2:CAVE2 + CAVE2_LEN] = CAVE2_DEV
    if not a.restore:
        wtt = shift_for(a.start)
        if a.version == 1:
            struct.pack_into("<I", d, SITE, bl(SITE, CAVE))
            d[CAVE:CAVE + CAVE_LEN] = struct.pack("<%dI" % (CAVE_LEN // 4), *cave_words(wtt))
        else:
            lts = day_shift_for(a.lts_start, FIRST_LTS, CUTOFF_LTS, "--lts-start")
            rnd = day_shift_for(a.round_start, FIRST_ROUND, LAST_ROUND_END, "--round-start")
            struct.pack_into("<I", d, SITE, bl(SITE, CAVE2))
            d[CAVE2:CAVE2 + CAVE2_LEN] = struct.pack("<%dI" % (CAVE2_LEN // 4), *cave2_words(wtt, lts, rnd))
    out = gzip.compress(bytes(d)) if a.out.endswith(".gz") else bytes(d)
    open(a.out, "wb").write(out)
    print(f"{a.out}: {state(d)}")


if __name__ == "__main__":
    main()
