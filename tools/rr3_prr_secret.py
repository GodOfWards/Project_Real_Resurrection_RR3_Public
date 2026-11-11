#!/usr/bin/env python3
"""Player secret for the Project Real Resurrection website login (issue
#220 part 1, #163), by patching libRealRacing3.so (v14.0.1, arm64,
develified build). Version 1, untested in game.
Guide: docs/prr-secret.md.

The phone makes 32 random bytes (getrandom) the first time it writes a
Cloudcell request header, keeps them in its own file,
files/doc/prr_secret.dat (never in the save), and adds them as
"rrsecret:<64 lowercase hex>" to every request header. tools/rr3_cc_server.py
v5.16 keeps the first secret each player sends; rr3_prr_login.py uses the
same file to log in on the website.

  0x1d04b24  Cloudcell request header writer 0x1d04438, after the device
             strings: `ldr x8, [x25]` -> `b 0x1583704` (secret_hdr). It reads
             the file (or makes it: missing, or not exactly 32 bytes),
             appends the string, runs the replaced instruction and goes back
             to 0x1d04b28. If no secret can be made and kept, the header is
             unchanged. rr3_username.py's hook (0x1d04b80) is a different
             site; the two strings are independent.
  0x1583704  new code (380 bytes, tools/asm/rr3_prr_secret.s) in this tool's
             slice 0x1583704..0x1583904 of the dead physics-state compare
             (tables/lib-code-caves.csv); the rest of the slice is zeroed so
             tools/rr3_patch_sites.py shows the whole slice as ours.
             rr3_prr_login.py and rr3_prr_social.py use the rest of the cave.

File format: 32 raw bytes, nothing else.

Usage:
  rr3_prr_secret.py check LIB
  rr3_prr_secret.py patch IN OUT [--restore]
  rr3_prr_secret.py show FILE           (a prr_secret.dat: the hex the server gets)
  rr3_prr_secret.py write FILE [HEX]    (make one, e.g. for a test; random if no HEX)
IN may be gzipped; OUT is written uncompressed (or gzipped if it ends in .gz).
"""
import argparse
import gzip
import os
import re
import struct
import sys

VERSION = 1
CAVE, SLICE_END = 0x1583704, 0x1583904
SECRET_HDR = CAVE
HOOK = 0x1D04B24
# tools/asm/rr3_prr_secret.s linked for 0x1583704 (build line in that file).
CODE = (
    0xA9A67BFD, 0x910003FD, 0x910283E0, 0x94000046, 0x910283E0, 0xF0FF7541,
    0x911FF821, 0x94225170, 0xB40001A0, 0xF9000BE0, 0xAA0003E3, 0x910083E0,
    0xD2800021, 0xD2800422, 0x942251D9, 0xF9000FE0, 0xF9400BE0, 0x9422516A,
    0xF9400FE0, 0xF100801F, 0x54000340, 0xD28022C0, 0x910083E1, 0xD2800402,
    0xD2800003, 0x9422587A, 0xF100801F, 0x54000561, 0x910283E0, 0xB0FF7401,
    0x91336821, 0x94225158, 0xB40004C0, 0xF9000BE0, 0xAA0003E3, 0x910083E0,
    0xD2800021, 0xD2800402, 0x94225179, 0xF9000FE0, 0xF9400BE0, 0x94225152,
    0x35000380, 0xF9400FE0, 0xF100801F, 0x54000321, 0x52800928, 0xB90053E8,
    0x10000489, 0xF9400128, 0xF80543E8, 0x39402128, 0x390173E8, 0x3000042C,
    0x910083E9, 0x910177EA, 0xD280040B, 0x3840152D, 0x53047DAE, 0x386E698E,
    0x3800154E, 0x12000DAD, 0x386D698D, 0x3800154D, 0xF100056B, 0x54FFFF01,
    0xAA1303E0, 0x910143E1, 0x528009A2, 0x941CE944, 0xA8DA7BFD, 0xF9400328,
    0x141E04C1, 0xA9BE7BFD, 0x910003FD, 0xF9000BE0, 0x97F487EF, 0xAA0003E3,
    0xF9400BE0, 0xD2802001, 0x30000142, 0x942257FA, 0xA8C27BFD, 0xD65F03C0,
    0x65737272, 0x74657263, 0x3231303A, 0x36353433, 0x61393837, 0x65646362,
    0x70732566, 0x735F7272, 0x65726365, 0x61642E74, 0x00000074,
)
# The words of the dead function in this tool's slice (128 words).
CAVE_DEVELIFIED = (
    0xA9BD7BFD, 0xF9000BF5, 0xA9024FF4, 0x910003FD, 0xF9400008, 0xF9400029,
    0xAA0103F3, 0xAA0003F4, 0xEB09011F, 0x1A9F17F5, 0x54000080, 0xF0FF70A0,
    0x912B5800, 0x97EC70B8, 0xB940D288, 0xB940D269, 0x6B09011F, 0x54000121,
    0xB940D688, 0xB940D669, 0x6B09011F, 0x540000A1, 0xB940DA88, 0xB940DA69,
    0x6B09011F, 0x540000A0, 0xD0FF7680, 0x9133B800, 0x97EC70A9, 0x2A1F03F5,
    0xB9410288, 0xB9410269, 0x6B09011F, 0x54000121, 0xB9410688, 0xB9410669,
    0x6B09011F, 0x540000A1, 0xB9410A88, 0xB9410A69, 0x6B09011F, 0x540000A0,
    0x90FF7860, 0x91325000, 0x97EC7099, 0x2A1F03F5, 0xB9411A88, 0xB9411A69,
    0x6B09011F, 0x540002C1, 0xB9411E88, 0xB9411E69, 0x6B09011F, 0x54000241,
    0xB9412288, 0xB9412269, 0x6B09011F, 0x540001C1, 0xB9412688, 0xB9412669,
    0x6B09011F, 0x54000241, 0xB9412A88, 0xB9412A69, 0x6B09011F, 0x540002C1,
    0xB9412E88, 0xB9412E69, 0x6B09011F, 0x54000340, 0x1400014E, 0xD0FF71C0,
    0x911C1400, 0x97EC707C, 0x2A1F03F5, 0xB9412688, 0xB9412669, 0x6B09011F,
    0x54FFFE00, 0xB0FF7140, 0x91157000, 0x97EC7074, 0x2A1F03F5, 0xB9412A88,
    0xB9412A69, 0x6B09011F, 0x54FFFD80, 0xD0FF7640, 0x91029C00, 0x97EC706C,
    0x2A1F03F5, 0xB9412E88, 0xB9412E69, 0x6B09011F, 0x540026C1, 0xB9413288,
    0xB9413269, 0x6B09011F, 0x54002641, 0xB9413688, 0xB9413669, 0x6B09011F,
    0x540025C1, 0xB9414688, 0xB9414669, 0x6B09011F, 0x54002641, 0xB9414A88,
    0xB9414A69, 0x6B09011F, 0x540026C1, 0xB9414E88, 0xB9414E69, 0x6B09011F,
    0x54002741, 0xB9415288, 0xB9415269, 0x6B09011F, 0x540027C1, 0xB9415688,
    0xB9415669, 0x6B09011F, 0x54002841, 0xB9415A88, 0xB9415A69, 0x6B09011F,
    0x540028C1, 0xB9415E88,
)
SLICE_WORDS = (SLICE_END - CAVE) // 4
# (address, develified words, {version: words}); a version not listed writes
# the develified words. .text VMA == file offset in this build.
PARTS = [
    # code + zeros to the end of the slice
    (CAVE, CAVE_DEVELIFIED, {1: CODE + (0,) * (SLICE_WORDS - len(CODE))}),
    # ldr x8, [x25] -> b secret_hdr
    (HOOK, (0xF9400328,), {1: (0x17E1FAF8,)}),
]
# The cave (tables/lib-code-caves.csv) requires nothing.
REQUIRES = []
SIZE = 32
HEX_RE = re.compile(r"[0-9a-fA-F]{64}")


def load(path):
    data = open(path, "rb").read()
    return bytearray(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def words(part, v):
    addr, develified, by_version = part
    return by_version.get(v, develified)


def version(d):
    """0 develified, 1 patched, None unrecognised."""
    have = [struct.unpack_from(f"<{len(p[1])}I", d, p[0]) for p in PARTS]
    for v in (0, 1):
        if all(h == words(p, v) for h, p in zip(have, PARTS)):
            return v
    return None


def state(d):
    v = version(d)
    if v is None:
        return None
    return f"patched v{v} (player secret in the request header)" if v else "develified"


def contents(d):
    """`patches` entry for rr3_build.py: '' develified, None unrecognised."""
    v = version(d)
    return None if v is None else "" if v == 0 else "prr-secret"


def show(path):
    b = open(path, "rb").read()
    if len(b) != SIZE:
        sys.exit(f"not a prr_secret.dat file ({len(b)} bytes, not {SIZE}): the game makes a new one")
    print(f"rrsecret:{b.hex()}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").add_argument("lib")
    p = sub.add_parser("patch")
    p.add_argument("inp")
    p.add_argument("out")
    p.add_argument("--restore", action="store_true", help="put the develified bytes back")
    sub.add_parser("show").add_argument("file")
    w = sub.add_parser("write")
    w.add_argument("file")
    w.add_argument("hex", nargs="?", help="64 hex digits (default: random)")
    a = ap.parse_args()

    if a.cmd == "show":
        show(a.file)
        return
    if a.cmd == "write":
        if a.hex is not None and not HEX_RE.fullmatch(a.hex):
            sys.exit("the secret is 64 hex digits")
        open(a.file, "wb").write(bytes.fromhex(a.hex) if a.hex else os.urandom(SIZE))
        show(a.file)
        return
    d = load(a.lib if a.cmd == "check" else a.inp)
    s = state(d)
    if s is None:
        sys.exit("unexpected bytes at a patch site or in the code area: not the v14.0.1 develified build?")
    if a.cmd == "check":
        print(s)
        return
    for p in PARTS:
        w = words(p, 0 if a.restore else VERSION)
        struct.pack_into(f"<{len(w)}I", d, p[0], *w)
    open(a.out, "wb").write(gzip.compress(bytes(d)) if a.out.endswith(".gz") else bytes(d))
    print(f"{a.out}: {state(d)}")


if __name__ == "__main__":
    main()
