#!/usr/bin/env python3
"""Remove Google Play from the game's own screens, in libRealRacing3.so
(v14.0.1, arm64, develified build). Issue #348, v2 (#464). Part of Project Real
Resurrection's work on Real Racing 3. Not affiliated with, endorsed or
supported by Electronic Arts.

Parts (--parts, comma-separated; default ui):

  ui        0xcd77e0 ("Google Play enabled": [[[GOT 0x1f6d5d8]]+0x10500]
            +0xe4 == 1) always returns 0. Its 9 callers skip their Google
            Play part: the green Sign in / Sign out buttons in Settings
            (setup 0x1514e98, refreshes 0x15158c8 and 0x151932c), the
            Google Play button of the tutorial login screen
            (RookieChampionship::SocialLoginScreen, 0x138c140), the Google
            Play part of SocialMediaLoginPopup (0x14f358c) and of the
            achievement screen (0xd3e678), and 0xaeb7f0, 0xd3d4b0, 0xdb98ec
            (not identified).

              0xcd77e0  adrp x8, 0x1f6d000      -> mov w0, #0  (d00094a8 -> 52800000)
              0xcd77e4  ldr  x8, [x8, #0x5d8]   -> ret         (f942ed08 -> d65f03c0)

            The "logged in?" checks 0xcd8578 / 0xcd8498 read the same field
            inline (not through 0xcd77e0) and only OR Google Play in; with
            rr3_prr_social.py Facebook already answers "logged in", so their
            71 callers see no change (analysis/google-play-games.md §4).

  fblogout  v1 only (v1's default; v2 leaves it out, because
            rr3_prr_login.py v2 reuses this button as the website button,
            issue #464). The Facebook Logout button in Settings (+0x2e8, widget 0x186d4)
            is hidden instead of shown on the logged-in branch of the
            social row refresh 0x1515764 (Login +0x2e0 is hidden on the same
            branch, so the row shows no Facebook button):

              0x15158b0 bl 0x10bd3d8 (Show) -> bl 0x10bd5f0 (Hide)  (97ee9eca -> 97ee9f50)

Research: analysis/google-play-games.md §4-§6. Guide: docs/no-gplay.md.
The Java side (Play Games SDK start-up, silent sign-in) is not changed here.

Usage:
  rr3_no_gplay.py check LIB
  rr3_no_gplay.py patch IN OUT [--version N] [--parts ui,fblogout] [--restore]
  (--restore without --parts restores every part)
IN may be gzipped; OUT is written uncompressed (or gzipped if it ends in .gz).
"""
import argparse
import gzip
import struct
import sys

VERSION = 2   # v1: default parts ui,fblogout; v2: default part ui only

# part -> [(site, develified word, patched word)]
PARTS = {
    "ui": [
        (0xCD77E0, 0xD00094A8, 0x52800000),     # adrp x8, 0x1f6d000    -> mov w0, #0
        (0xCD77E4, 0xF942ED08, 0xD65F03C0),     # ldr x8, [x8, #0x5d8]  -> ret
    ],
    "fblogout": [
        (0x15158B0, 0x97EE9ECA, 0x97EE9F50),    # bl 0x10bd3d8 (Show)   -> bl 0x10bd5f0 (Hide)
    ],
}
WHAT = {"ui": "Google Play buttons and prompts",
        "fblogout": "Facebook Logout button in Settings"}
DEFAULT_PARTS = ["ui"]
# --version 1 writes v1's default (both parts).
VERSION_PARTS = {1: ["ui", "fblogout"], 2: DEFAULT_PARTS}


def load(path):
    data = open(path, "rb").read()
    return bytearray(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def part_state(d, part):
    """0 develified, 1 patched (v1), None unrecognised."""
    words = [struct.unpack_from("<I", d, s)[0] for s, _, _ in PARTS[part]]
    if words == [o for _, o, _ in PARTS[part]]:
        return 0
    if words == [n for _, _, n in PARTS[part]]:
        return 1
    return None


def contents(d):
    """`patches` entry for rr3_build.py: '' develified, None unrecognised.
    e.g. no-gplay=ui+fblogout (only revisions carry @vN)."""
    st = {p: part_state(d, p) for p in PARTS}
    if None in st.values():
        return None
    on = [p for p in PARTS if st[p]]
    return "no-gplay=" + "+".join(on) if on else ""


def describe(d):
    return {p: {0: "develified", 1: "patched"}.get(part_state(d, p), "unrecognised")
            for p in PARTS}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("lib")
    p = sub.add_parser("patch")
    p.add_argument("inp")
    p.add_argument("out")
    p.add_argument("--parts", default=None,
                   help="comma-separated: " + ", ".join(PARTS) + f" (default {','.join(DEFAULT_PARTS)})")
    p.add_argument("--version", type=int, choices=sorted(VERSION_PARTS), default=VERSION,
                   help="default parts of this version (1: ui,fblogout; 2: ui)")
    p.add_argument("--restore", action="store_true", help="put the develified instructions back")
    a = ap.parse_args()

    d = load(a.lib if a.cmd == "check" else a.inp)
    state = describe(d)
    for n, s in state.items():
        if s == "unrecognised":
            sys.exit(f"{n}: unexpected bytes: not the v14.0.1 develified build?")
    if a.cmd == "check":
        for n, s in state.items():
            print(f"{n} ({WHAT[n]}): {s}")
        return
    if a.parts is not None:
        parts = [x for x in a.parts.split(",") if x]
    else:   # --restore without --parts puts every part back
        parts = list(PARTS) if a.restore else VERSION_PARTS[a.version]
    for n in parts:
        if n not in PARTS:
            sys.exit(f"unknown part {n}: choose from {', '.join(PARTS)}")
    for n in parts:
        for site, develified, patched in PARTS[n]:
            struct.pack_into("<I", d, site, develified if a.restore else patched)
    out = gzip.compress(bytes(d)) if a.out.endswith(".gz") else bytes(d)
    open(a.out, "wb").write(out)
    print(f"{a.out}: " + ", ".join(f"{n} {s}" for n, s in describe(d).items()))


if __name__ == "__main__":
    main()
