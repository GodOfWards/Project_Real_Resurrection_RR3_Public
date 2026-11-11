#!/usr/bin/env python3
"""Keep "someone beat your time" mail for every event, in libRealRacing3.so
(v14.0.1, arm64, develified build). Issue #163.

The mail reply (subsync 10459, callback 0x1357200) keeps a mail only when
the event already has an entry in RacerManager's friends map (RM+0xf8) or a
friend results file res_<event>.pld. Entries are made only by the reader of
the 10419 reply (friends' results), and without social friends the phone
sends 10419 for few events (analysis/friends.md 2.1), so every other mail
is dropped (seen 2026-10-24: two mails for Dubai Oval 3702 sent, none
shown).

Per mail, the reader looks the event up in the map itself (0x135734c ..
0x1357380), then calls 0x1356c68 (load res_<event>.pld) and skips the mail
when that returns 0. This patch calls 0x1351d90(RM, event, create = 1)
instead, the function the 10419 reader uses (0x1353200): it finds the map
entry, or loads the file, or makes an empty entry, and returns it. The
reader's own lookup is skipped (0x1351d90 does the same lookup and the
same sort, 0x134c308):

  0x135734c  ldr  x9, [x26]       -> mov w2, #1         (f9400349 -> 52800022)
  0x1357350  cbz  x9, 0x1357384   -> b   0x1357384      (b40001a9 -> 1400000d)
  0x135738c  bl   0x1356c68       -> bl  0x1351d90      (97fffe37 -> 97ffea81)

The new entry has no rows apart from the mail sender's; it is not saved
(no res_<event>.pld). The next 10419 answer for the event replaces it.
Which mails the game then shows is still filtered by 0xe0152c
(analysis/leaderboard-ghosts.md 7.2).

Usage:
  rr3_friends_mail.py check LIB
  rr3_friends_mail.py patch IN OUT [--restore]
IN may be gzipped; OUT is written uncompressed (or gzipped if it ends in .gz).
"""
import argparse
import gzip
import struct
import sys

# (site, develified word, patched word)
SITES = [
    (0x135734C, 0xF9400349, 0x52800022),    # ldr x9, [x26]     -> mov w2, #1
    (0x1357350, 0xB40001A9, 0x1400000D),    # cbz x9, 0x1357384 -> b 0x1357384
    (0x135738C, 0x97FFFE37, 0x97FFEA81),    # bl 0x1356c68      -> bl 0x1351d90
]


def load(path):
    data = open(path, "rb").read()
    return bytearray(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def raw_state(d):
    """'develified', 'patched' or None (unrecognised)."""
    words = [struct.unpack_from("<I", d, site)[0] for site, _, _ in SITES]
    if words == [s for _, s, _ in SITES]:
        return "develified"
    if words == [p for _, _, p in SITES]:
        return "patched"
    return None


def state(d):
    return {"develified": "develified (mail kept only for events with friends' results)",
            "patched": "patched (mail kept for every event)"}.get(raw_state(d))


def contents(d):
    """`patches` entry for rr3_build.py: '' develified, None unrecognised."""
    return {"develified": "", "patched": "friends-mail"}.get(raw_state(d))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("lib")
    p = sub.add_parser("patch")
    p.add_argument("inp")
    p.add_argument("out")
    p.add_argument("--restore", action="store_true", help="put the develified instructions back")
    a = ap.parse_args()

    d = load(a.lib if a.cmd == "check" else a.inp)
    if state(d) is None:
        sys.exit("unexpected bytes at 0x135734c..0x135738c: not the v14.0.1 develified build?")
    if a.cmd == "check":
        print(state(d))
        return
    for site, develified, patched in SITES:
        struct.pack_into("<I", d, site, develified if a.restore else patched)
    out = gzip.compress(bytes(d)) if a.out.endswith(".gz") else bytes(d)
    open(a.out, "wb").write(out)
    print(f"{a.out}: {state(d)}")


if __name__ == "__main__":
    main()
