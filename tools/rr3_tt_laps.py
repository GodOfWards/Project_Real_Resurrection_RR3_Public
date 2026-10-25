#!/usr/bin/env python3
"""Let Time Trial run more than one lap by patching libRealRacing3.so (v14.0.1, arm64).

Time Trial does not use the race lap count. TimeTrialMode keeps a lap-timing
object at +0x1b0 (ctor 0x102ebd0, tick 0x102ea04, only caller 0x1043444).
Its tick counts finish-line crossings in +0x154 (reset to 0 when the timed
lap starts) and, on the next crossing, does:

  0x102ea8c  tbnz w8, #31, 0x102eb50   ; w8 = crossings before this one
             ...record lap...           ; skipped while w8 < 0
             mov  w8, #2 / str w8, [x19] ; state 2 = finished -> results

The patch changes that one instruction to `tbz w8, #k, 0x102eb50`: a crossing
only finishes the session once bit k of the count is set, i.e. after
2**k + 1 laps. Intermediate laps go down the existing "not finished" path,
so they aren't recorded as lap times. k = 30 never finishes; leave through
the pause menu.

`--laps reset` instead makes it `b 0x102eb08`, the path the first crossing
takes to start the timed lap: every crossing restarts the lap timer, so the
on-screen time starts from zero each lap. Never finishes either.

`--laps best` keeps 0x102ea8c stock and hooks the finish path instead
(0x102eab4, `ldr x0, [x19, #0x60]` -> `b CAVE`). The cave (in the 4 KiB
alignment padding at 0x1ac0b40) reads the lap just recorded (0x102e5bc) and
the stored best for the current event (the same lookup the results screen
uses at 0x1043c8c: game+0x478 -> 0x152dc60 -> 0x9bb760(mgr, event) -> +8).
A lap that beats it (or no stored best) takes the stock finish, so the game
files it as usual; any other lap restarts the timer via 0x102eb08. Before
restarting, the cave sets every slot of the player recording's node-time table
(recorder TT+0x388 -> +0x10 -> +0x17708) back to -1. The recorder tick
(0x159f754) only fills empty (negative) slots and nothing else clears them
between laps, so without this a new best saved after restarted laps kept the
first lap's times and the live delta compared against that slower lap.

v4 first checks the session's validity field TimeTrialMode+0x5fc (timing
+0x44c): -1 = valid, 0 = off track, 2 = too much damage. It is set once by the
off-track (0x1041a74) and damage (0x1041f90) handlers and checked by the
finish handler before saving. An invalid lap is never a best: the cave sets
the field back to -1 and restarts the lap (with the node-time clear), so only
that lap is lost instead of the whole session.

`--best-version N` writes an older `best` cave (2, 3 or 4) so each fix can
be tested on its own; without it the latest (v4) is written.

Usage:
  rr3_tt_laps.py check LIB
  rr3_tt_laps.py patch IN OUT --laps {2,3,5,9,17,unlimited,reset,best} [--best-version {2,3,4}]
IN may be gzipped; OUT is written uncompressed (or gzipped if it ends in .gz).
"""
import argparse
import gzip
import re
import struct
import sys

SITE = 0x102EA8C                 # .text VMA == file offset in this build
STOCK = 0x37F80628               # tbnz w8, #31, 0x102eb50
RESTART = 0x1400001F             # b 0x102eb08 (start-of-timed-lap path)
HOOK = 0x102EAB4                 # ldr x0, [x19, #0x60] in the finish path
HOOK_STOCK = 0xF9403260
CAVE = 0x1AC0B40                 # zero padding before the page-aligned 0x1ac1000
# Assembled with llvm-mc; source and addresses in analysis/libRealRacing3.so.md.
CAVE_CODE = bytes.fromhex(
    "694e44b93f0500318000005409008012694e04b918000014f50f1ff8e00313aa"
    "97b6d597f503002a68825df8097482522900a072016969f8810100b400e11191"
    "38b4e997f7eabb97000100b4090840b93f010071ad000054bf02096b6b000054"
    "f50741f804000014f50741f8603240f9c2b7d51768ee40f9680100b4080940f9"
    "280100b4085d409108211c91092940a90b0080123f010aeb620000542b4500b8"
    "fdffff17c9b7d517"
)
# Earlier cave (v3): an off-track or damage lap kept the whole session invalid
# (TT+0x5fc), so a later new best showed "Time not recorded".
CAVE_CODE_V3 = bytes.fromhex(
    "f50f1ff8e00313aa9db6d597f503002a68825df8097482522900a072016969f8"
    "810100b400e111913eb4e997fdeabb97000100b4090840b93f010071ad000054"
    "bf02096b6b000054f50741f804000014f50741f8603240f9c8b7d51768ee40f9"
    "680100b4080940f9280100b4085d409108211c91092940a90b0080123f010aeb"
    "620000542b4500b8fdffff17cfb7d517"
)
# Earlier cave (v2): restarted the lap without clearing the node-time table,
# so a best set after a restarted lap saved a ghost with stale delta times.
CAVE_CODE_V2 = bytes.fromhex(
    "f50f1ff8e00313aa9db6d597f503002a68825df8097482522900a072016969f8"
    "810100b400e111913eb4e997fdeabb97000100b4090840b93f010071ad000054"
    "bf02096b6b000054f50741f8dfb7d517f50741f8603240f9c8b7d517"
)
# `best` caves by version; patch writes BEST_LATEST unless --best-version picks one.
BEST = {
    4: (CAVE_CODE, "unlimited until a valid lap beats the stored best"),
    3: (CAVE_CODE_V3, "one invalid lap voids the session"),
    2: (CAVE_CODE_V2, "stale live delta after restarted laps"),
}
BEST_LATEST = max(BEST)
HOOK_CODE = 0x142A4823           # b 0x1ac0b40
LAPS = {"2": 0, "3": 1, "5": 2, "9": 3, "17": 4, "unlimited": 30}


def load(path):
    data = open(path, "rb").read()
    return bytearray(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def insn(bit):
    """tbz w8, #bit, 0x102eb50 (same target and register as the stock tbnz)."""
    return (STOCK & ~(1 << 24) & ~(31 << 19)) | (bit << 19)


def state(d):
    w, = struct.unpack_from("<I", d, SITE)
    h, = struct.unpack_from("<I", d, HOOK)
    for ver, (code, desc) in BEST.items():
        if h == HOOK_CODE and w == STOCK and d[CAVE:CAVE + len(CAVE_CODE)] == code + bytes(len(CAVE_CODE) - len(code)):
            return f"patched (best v{ver}{'' if ver == BEST_LATEST else ', older'}: {desc})"
    if h != HOOK_STOCK or any(d[CAVE:CAVE + len(CAVE_CODE)]):
        return None
    if w == STOCK:
        return "stock (1 lap)"
    if w == RESTART:
        return "patched (unlimited, lap timer resets each lap)"
    for name, bit in LAPS.items():
        if w == insn(bit):
            return f"patched ({name} laps)"
    return None


def contents(d):
    """`patches` entry for rr3_build.py: '' stock, None unrecognised."""
    s = state(d)
    if s is None or s.startswith("stock"):
        return None if s is None else ""
    m = re.search(r"best v(\d+)", s)
    if m:
        return "tt-laps=best" + ("" if m.group(1) == "1" else "@v" + m.group(1))
    if "unlimited, lap timer" in s:
        return "tt-laps=reset"
    return "tt-laps=" + re.search(r"\((\w+) laps\)", s).group(1)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("lib")
    p = sub.add_parser("patch")
    p.add_argument("inp")
    p.add_argument("out")
    p.add_argument("--laps", choices=[*LAPS, "reset", "best"], required=True)
    p.add_argument("--best-version", type=int, choices=sorted(BEST), help=f"`best` cave version (default: latest, {BEST_LATEST})")
    a = ap.parse_args()

    d = load(a.lib if a.cmd == "check" else a.inp)
    cur = state(d)
    if a.cmd == "check":
        print("Time Trial:", cur or "unrecognised code at 0x102ea8c / 0x102eab4")
        return
    if cur != "stock (1 lap)":
        raise SystemExit(f"input must be the stock library (it is: {cur or 'unrecognised'})")
    if a.cmd == "patch" and a.best_version and a.laps != "best":
        raise SystemExit("--best-version only goes with --laps best")
    if a.laps == "best":
        code = BEST[a.best_version or BEST_LATEST][0]
        d[CAVE:CAVE + len(code)] = code
        struct.pack_into("<I", d, HOOK, HOOK_CODE)
    else:
        struct.pack_into("<I", d, SITE, RESTART if a.laps == "reset" else insn(LAPS[a.laps]))
    open(a.out, "wb").write(gzip.compress(bytes(d)) if a.out.endswith(".gz") else bytes(d))
    after = state(d)
    print(f"Time Trial: {cur} -> {after}; wrote {a.out}")


if __name__ == "__main__":
    sys.exit(main())
