#!/usr/bin/env python3
"""Offline mode for libRealRacing3.so (v14.0.1, arm64, develified build).
Issue #309, v1. Part of Project Real Resurrection's work on Real Racing 3.
Not affiliated with, endorsed or supported by Electronic Arts.

With the debug menu entry PRR|Offline (restart): ON (rr3_debug_menu.py
settings v5: the .bss byte of static entry 196, GOT 0x1f6e5e0, kept in
files/doc/debug_menu_settings.dat and set at start), the game stops trying
to reach any server from the next start, and nothing waits on a timeout:

  H1 0x1cd59b0  StartListDownload `ldrb w8, [x20, #0x21]` -> bl h1: the
                request's load-only byte reads 1, so EA's "Asset download
                skipped - load only!" path runs (no download, no per-asset
                error). Assets already on the phone work.
  H2 0x1ce1c5c  HttpRequestManager post, after its shutting-down check,
                `mov x21, x0` -> bl h2: every Cloudcell request's URL
                (syncs, /time, packs, /assetman/) becomes
                http://127.0.0.1:1/. Android refuses it at once, nothing
                leaves the phone, and Java's errorCallback runs once, as on
                a phone with no network.
  H3 0x1cf53a8  reachability getter 0x1cf537c, `mov w0, w19` -> b h3:
                returns 1 (no network) whatever Java reported, so EA's own
                offline screens, prompts and browser/news block follow.
  H4 0xbb0f00   OMP master connect 0xbb0ed8, `mov x20, x1` -> bl h4: the
                host is 127.0.0.1, so the UDP hello never leaves the phone
                (rr3_omp.py's port words 0xbb0f88/0xbb1020/0xbb4504 stay).
  H5 0x1cbfefc  cached MAC getter 0x1cbfed0, `cbnz x8, 0x1cc0030` -> b h5:
                the cached (empty) string is returned without calling Java
                GetDeviceMacAddress(), so attest-dex's PrrAttest never
                starts and /prr/attest is never sent. Nothing compares the
                MAC between starts (analysis/offline-mode.md section 6).

With the byte 0 every hook does what the game did. New code
(tools/asm/rr3_offline.s) at 0xfec9c8..0xfecaa8, this tool's slice
0xfec9c4..0xfecac4 of the dead benchmark-table function (cave
0xfec9c4..0xfede6c, tables/lib-code-caves.csv).

Not covered: Java SDK traffic (EA/Glu hosts are dead; Firebase and ads would
need an APK change) and the OMP master's DNS lookup at start (0xbb4504 path).

Needs rr3_debug_menu.py settings v5 (the menu entry and the flag): `patch`
refuses a lib without it. Research: analysis/offline-mode.md. Guide:
docs/offline-mode.md.

Usage:
  rr3_offline.py check LIB
  rr3_offline.py patch IN OUT [--restore]
IN may be gzipped; OUT is written uncompressed (or gzipped if it ends in .gz).
"""
import argparse
import gzip
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rr3_debug_menu  # noqa: E402  (settings v5: the offline flag)

VERSION = 1
# Code caves this tool writes in need these (tables/lib-code-caves.csv); the
# benchmark-table function needs nothing.
REQUIRES = []

CAVE_AT = 0xFEC9C8
CAVE_END = 0xFECAC4
# tools/asm/rr3_offline.s linked for 0xfec9c8 (build line in that file).
CAVE = (
    0x39408688, 0xD0007C09, 0xF942F129, 0x39400129, 0x2A090108, 0xD65F03C0,
    0xAA0003F5, 0xD0007C09, 0xF942F129, 0x39400129, 0x340001E9, 0x3940402A,
    0x360000AA, 0xF940102C, 0xD280026A, 0xF9000C2A, 0x14000004, 0x9100442C,
    0x528004CA, 0x3900402A, 0x1000038D, 0xA9402DAA, 0xA9002D8A, 0xB94011AA,
    0xB900118A, 0xD65F03C0, 0x2A1303E0, 0xD0007C09, 0xF942F129, 0x39400129,
    0x34000049, 0x52800020, 0xA8C24FF4, 0xD65F03C0, 0xAA0103F4, 0xD0007C09,
    0xF942F129, 0x39400129, 0x34000049, 0x100001D4, 0xD65F03C0, 0xB50000C8,
    0xD0007C09, 0xF942F129, 0x39400129, 0x35000049, 0x14334D20, 0x14334D6B,
    0x70747468, 0x312F2F3A, 0x302E3732, 0x312E302E, 0x002F313A, 0x2E373231,
    0x2E302E30, 0x00000031,
)
# The develified words of the slice (dead code).
CAVE_DEVELIFIED = (
    0xA9057BFD, 0xA9065FF8, 0xA90757F6, 0xA9084FF4, 0x910143FD, 0xD53BD056,
    0xF94016C8, 0x910043F8, 0x91002314, 0xF0FF9EA1, 0xAA0003F5, 0x91070013,
    0x0F030480, 0x52800029, 0x9102D421, 0xAA1403E0, 0xF81F83A8, 0xA901FFFF,
    0xF90017FF, 0xFD001BE0, 0xA903FFFF, 0xB90013E9, 0x9417B593, 0xB0FF9CE8,
    0x3DC2AD00, 0xB90043FF, 0x910722B7, 0x3D800FE0, 0xA95CA6A8, 0x910742B5,
    0x3D8003E0, 0xEB09011F, 0x54000222, 0xB94013E9, 0x9100830A, 0xB9000109,
    0xF9400A89, 0x3DC00280, 0xF9000D09, 0x3C808100, 0xA900FE9F, 0xF900029F,
    0xF9400949, 0x3DC00140, 0x9100E10A, 0xF9001909, 0x3D800900, 0xF90002EA,
    0x14000008, 0x910043E1, 0xAA1303E0, 0x940008F2, 0x394063E8, 0x36000068,
    0xF94017E0, 0x9438AC2B,
)
# (site, develified words, patched words)
SITES = [
    (0x1CD59B0, (0x39408688,), (0x97CC5C06,)),   # H1 ldrb w8, [x20, #0x21]  -> bl 0xfec9c8 (h1)
    (0x1CE1C5C, (0xAA0003F5,), (0x97CC2B61,)),   # H2 mov x21, x0            -> bl 0xfec9e0 (h2)
    (0x1CF53A8, (0x2A1303E0,), (0x17CBDDA2,)),   # H3 mov w0, w19            -> b 0xfeca30 (h3)
    (0xBB0F00, (0xAA0103F4,), (0x9410EED4,)),    # H4 mov x20, x1            -> bl 0xfeca50 (h4)
    (0x1CBFEFC, (0xB50009A8,), (0x17CCB2DC,)),   # H5 cbnz x8, 0x1cc0030     -> b 0xfeca6c (h5)
    (CAVE_AT, CAVE_DEVELIFIED, CAVE),
]
assert CAVE_AT + 4 * len(CAVE) <= CAVE_END and len(CAVE) == len(CAVE_DEVELIFIED)


def load(path):
    data = open(path, "rb").read()
    return bytearray(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def state(d):
    """0 develified, 1 patched (v1), None unrecognised."""
    got = set()
    for site, develified, patched in SITES:
        w = struct.unpack_from(f"<{len(develified)}I", d, site)
        got.add(0 if w == develified else 1 if w == patched else None)
    return got.pop() if len(got) == 1 else None


def contents(d):
    """`patches` entry for rr3_build.py: '' develified, None unrecognised.
    v1 is 'offline' (only revisions carry @vN)."""
    s = state(d)
    return None if s is None else ("offline" if s else "")


def describe(d):
    return {0: "develified", 1: f"patched v{VERSION}"}.get(state(d), "unrecognised")


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
        sys.exit("offline: unexpected bytes: not the v14.0.1 develified build?")
    if a.cmd == "check":
        print(f"offline (PRR|Offline stops all server traffic): {describe(d)}")
        return
    if not a.restore and rr3_debug_menu.settings_version(d) != 5:
        sys.exit("offline needs rr3_debug_menu.py settings v5 (the PRR|Offline entry and its flag): "
                 "patch the debug menu first")
    for site, develified, patched in SITES:
        w = develified if a.restore else patched
        struct.pack_into(f"<{len(w)}I", d, site, *w)
    out = gzip.compress(bytes(d)) if a.out.endswith(".gz") else bytes(d)
    open(a.out, "wb").write(out)
    print(f"{a.out}: offline {describe(d)}")


if __name__ == "__main__":
    main()
