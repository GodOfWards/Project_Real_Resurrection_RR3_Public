#!/usr/bin/env python3
"""Stop the "PLEASE LOG IN" pop-up that Real Racing 3 shows when a Time Trial
leaderboard opens and the player is not logged in to a platform account or
social network, in libRealRacing3.so (v14.0.1, arm64, develified build).

The pop-up (title GAMETEXT_PLEASE_LOG_IN, text GAMETEXT_LOG_IN_REQUIRED:
"You need to be logged in to submit Time Trial results to the
leaderboards...") is opened by the leaderboard screen code at 0xdcabf4,
once per game start (flag byte 0x1f9d480, cleared at 0xdcac50). Before it,
0xdcaba0 calls the logged-in check 0x13833cc and skips the pop-up when it
returns true:

  0xdcaba4  tbnz w0, #0, 0xdcad88    (37000f20)

This patch makes that branch unconditional:

  0xdcaba4  b    0xdcad88            (14000079)

Only this one pop-up changes. The logged-in check itself (169 callers) is
untouched, so the game still does not upload Time Trial results itself; the
local test server reads them from the race history instead
(docs/cloudcell-test-server.md).

Usage:
  rr3_login_popup.py check LIB
  rr3_login_popup.py patch IN OUT [--restore]
IN may be gzipped; OUT is written uncompressed (or gzipped if it ends in .gz).
"""
import argparse
import gzip
import struct
import sys

SITE = 0xDCABA4
DEVELIFIED = 0x37000F20      # tbnz w0, #0, 0xdcad88
PATCHED = 0x14000079    # b 0xdcad88


def load(path):
    data = open(path, "rb").read()
    return bytearray(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def state(d):
    w = struct.unpack_from("<I", d, SITE)[0]
    return {DEVELIFIED: "develified (pop-up shown when not logged in)",
            PATCHED: "patched (no log-in pop-up)"}.get(w)


def contents(d):
    """`patches` entry for rr3_build.py: '' develified, None unrecognised."""
    w = struct.unpack_from("<I", d, SITE)[0]
    return {DEVELIFIED: "", PATCHED: "no-login-popup"}.get(w)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("lib")
    p = sub.add_parser("patch")
    p.add_argument("inp")
    p.add_argument("out")
    p.add_argument("--restore", action="store_true", help="put the develified instruction back")
    a = ap.parse_args()

    d = load(a.lib if a.cmd == "check" else a.inp)
    if state(d) is None:
        sys.exit("unexpected bytes at 0xdcaba4: not the v14.0.1 develified build?")
    if a.cmd == "check":
        print(state(d))
        return
    struct.pack_into("<I", d, SITE, DEVELIFIED if a.restore else PATCHED)
    out = gzip.compress(bytes(d)) if a.out.endswith(".gz") else bytes(d)
    open(a.out, "wb").write(out)
    print(f"{a.out}: {state(d)}")


if __name__ == "__main__":
    main()
