#!/usr/bin/env python3
"""Website login from the game's menus (issues #220 part 2, #163, #464), by
patching libRealRacing3.so (v14.0.1, arm64, develified build). Version 3,
untested in game (v1 works in game since b48; v2 is in b53).
Guide: docs/prr-login.md.

Opens the Project Real Resurrection website already logged in:

  https://rr3-upload.devel60.net/prr/login?v=1&m=<member>&c=<code>

code = the first 16 bytes, as 32 lowercase hex, of HMAC-SHA256(secret,
"login" + u32 member + u64 floor(time() / 60)), little-endian
(tools/rr3_cc_server.py login_code, v5.16). The secret is the file
rr3_prr_secret.py keeps, files/doc/prr_secret.dat. Nothing opens while the
member id is 1 (no server reply yet) or without a 32-byte secret file.

v1: the debug menu entry "Web Browser|F1 Signup / Internal Browser" becomes
"Web Browser|PRR Website / Friends, Login" (in-game browser).

  0xe548c0   the entry's std::function body: `sub sp, sp, #0x60` ->
             `b 0x1583904` (login).
  0x3a8f16   .rodata label, 38 bytes, used only by this entry.
  0x1583904  new code (tools/asm/rr3_prr_login.s) in this tool's slice
             0x1583904..0x1583d04 (1024 bytes) of the dead physics-state
             compare (tables/lib-code-caves.csv); the rest of the slice is
             zeroed. It reads the member id (as the Settings screen does,
             0x10a3b34), the secret file, time() (0x1e17c70), calls
             hmac_sha256 (0x163651c), formats the URL and opens it with
             0x1cbcb14(url, title), title "Project Real Resurrection".

v2 keeps all of v1 (the debug entry stays until the Settings button passes
in game) and adds two buttons (#464):

  Settings > Facebook Logout (widget 0x186d4, bottom social row) opens the
  site in the in-game browser instead of logging out. Its label 0x186ba
  reads SET_TEXT, the Facebook logo on it (0x186bb) is hidden; the blue
  button stays. The game shows this button only while Facebook counts as
  logged in (rr3_prr_social.py) and not in a race; rr3_no_gplay.py v1's
  part fblogout hides it (use rr3_no_gplay.py v2).

    0x1515e98  ldr x0, [x19, #0x2f0]; cbz x0, +8 -> bl login; b 0x1516394
    0x1514be0  str x0, [x19, #0x2e8] -> bl set_hook (setup: relabel, hide logo)

  Community > Get Support opens the site in the phone's browser
  (0x1cbc61c), logged in, after the screen's own connection check. Its
  label 0x4e34 reads COM_TEXT, the EA Help logo (0x4e40) is hidden.

    0xd6d710   adrp x8, ...; ldr x8, [x8, #0x630] -> bl login_ext; b 0xd6d934
    0xd6de34   bl 0x106aa4c (hide ticket dot) -> bl com_hook (same call,
               then relabel, hide logo)

  In the slice: `login`'s `bl OPEN_URL` becomes `bl open_sel`, which opens
  the phone's browser when x21 holds a marker that only `login_ext` sets
  (it restores the caller's x21), else the in-game browser as in v1. Then
  login_ext, set_hook, com_hook, relabel (as rr3_username.py v4) and hide.
  Texts are English in every language.

v3 (#145) = v2 without the Community > Get Support button: its two
Community sites (0xd6d710, 0xd6de34) stay develified, for rr3_community.py
(Get Support becomes Real Racing 3 on Reddit). The code in the slice is
v2's, unchanged; login_ext and com_hook are no longer called. The PRR
website stays on Settings > Facebook Logout and the debug menu entry.
v1 and v3 leave whatever is at the Community sites (develified or
rr3_community.py's) and only take back v2's own bytes there.

A limited debug menu (rr3_debug_menu.py --limited) shows the entry from
trim v2 on (prefix "Web Browser|PRR"); trim v1 hides it.

Usage:
  rr3_prr_login.py check LIB
  rr3_prr_login.py patch IN OUT [--version N] [--restore]
  rr3_prr_login.py url SECRET_FILE MEMBER [UNIX_TIME]   (the URL the game opens)
IN may be gzipped; OUT is written uncompressed (or gzipped if it ends in .gz).
"""
import argparse
import gzip
import hashlib
import hmac
import struct
import sys
import time

VERSION = 3
VERSIONS = (1, 2, 3)
CAVE, SLICE_END = 0x1583904, 0x1583D04
LOGIN = CAVE
LOGIN_EXT, SET_HOOK, COM_HOOK = 0x1583B1C, 0x1583B40, 0x1583B7C
SET_TEXT = "PRR Friends / Login"
COM_TEXT = "PRR Website (browser)"
# rr3_no_gplay.py part fblogout (v1 default): hides the button v2 reuses.
FBLOGOUT_SITE, FBLOGOUT_HIDE = 0x15158B0, 0x97EE9F50
HANDLER = 0xE548C0
LABEL = 0x3A8F16
LABEL_DEVELIFIED = b"Web Browser|F1 Signup\nInternal Browser"
LABEL_NEW = b"Web Browser|PRR Website\nFriends, Login"
URL = "https://rr3-upload.devel60.net/prr/login?v=1&m={member}&c={code}"
TITLE = "Project Real Resurrection"
# v1: tools/asm/rr3_prr_login.s up to `title` (v1 build, `bl OPEN_URL`).
CODE = (
    0xD109C3FF, 0xA9007BFD, 0x910003FD, 0xA90153F3, 0xD0004F48, 0xF942E908,
    0xF9400108, 0xF9401500, 0xF9400008, 0xF9404108, 0xD63F0100, 0xF9400008,
    0xF9401108, 0xD63F0100, 0xB9400013, 0x7100067F, 0x540009C0, 0x9105C3E0,
    0x97F487A9, 0xAA0003E3, 0x9105C3E0, 0xD2802001, 0x30000A22, 0x942257B4,
    0x9105C3E0, 0xF0FF7541, 0x911FF821, 0x942250DC, 0xB4000840, 0xF90013E0,
    0xAA0003E3, 0x910183E0, 0xD2800021, 0xD2800422, 0x94225145, 0xF90017E0,
    0xF94013E0, 0x942250D6, 0xF94017E0, 0xF100801F, 0x540006C1, 0xD2800000,
    0x942250B1, 0xD2800789, 0x9AC90814, 0x100006A9, 0xB9400128, 0xB90093E8,
    0x39401128, 0x390253E8, 0xB80953F3, 0xF80993F4, 0x9102A3E0, 0x910243E1,
    0xD2800222, 0x910183E3, 0xD2800404, 0x9402CACD, 0x3000052C, 0x9102A3E9,
    0x910323EA, 0xD280020B, 0x3840152D, 0x53047DAE, 0x386E698E, 0x3800154E,
    0x12000DAD, 0x386D698D, 0x3800154D, 0xF100056B, 0x54FFFF01, 0x3900015F,
    0x9103C3E0, 0xD2801001, 0x50000422, 0x2A1303E3, 0x910323E4, 0x9422577E,
    0x51000408, 0x7101F91F, 0x540001C8, 0xD2801028, 0x93407C09, 0x9103C3EA,
    0xA90327E8, 0xF90023EA, 0xD2800428, 0xD2800329, 0x3000042A, 0xA904A7E8,
    0xF9002FEA, 0x9100C3E0, 0x910123E1, 0x941CE427, 0xA94153F3, 0xA9407BFD,
    0x9109C3FF, 0xD65F03C0, 0x69676F6C, 0x3231306E, 0x36353433, 0x61393837,
    0x65646362, 0x70732566, 0x735F7272, 0x65726365, 0x61642E74, 0x74680074,
    0x3A737074, 0x72722F2F, 0x70752D33, 0x64616F6C, 0x7665642E, 0x30366C65,
    0x74656E2E, 0x7272702F, 0x676F6C2F, 0x763F6E69, 0x6D26313D, 0x2675253D,
    0x73253D63, 0x6F725000, 0x7463656A, 0x61655220, 0x6552206C, 0x72727573,
    0x69746365, 0x00006E6F,
)
# tools/asm/rr3_prr_login.s v2 linked for 0x1583904 (build line in that file):
# v1's words with word 93 (`bl OPEN_URL`) -> `bl open_sel`, then the v2 code.
CODE_V2 = (
    0xD109C3FF, 0xA9007BFD, 0x910003FD, 0xA90153F3, 0xD0004F48, 0xF942E908,
    0xF9400108, 0xF9401500, 0xF9400008, 0xF9404108, 0xD63F0100, 0xF9400008,
    0xF9401108, 0xD63F0100, 0xB9400013, 0x7100067F, 0x540009C0, 0x9105C3E0,
    0x97F487A9, 0xAA0003E3, 0x9105C3E0, 0xD2802001, 0x30000A22, 0x942257B4,
    0x9105C3E0, 0xF0FF7541, 0x911FF821, 0x942250DC, 0xB4000840, 0xF90013E0,
    0xAA0003E3, 0x910183E0, 0xD2800021, 0xD2800422, 0x94225145, 0xF90017E0,
    0xF94013E0, 0x942250D6, 0xF94017E0, 0xF100801F, 0x540006C1, 0xD2800000,
    0x942250B1, 0xD2800789, 0x9AC90814, 0x100006A9, 0xB9400128, 0xB90093E8,
    0x39401128, 0x390253E8, 0xB80953F3, 0xF80993F4, 0x9102A3E0, 0x910243E1,
    0xD2800222, 0x910183E3, 0xD2800404, 0x9402CACD, 0x3000052C, 0x9102A3E9,
    0x910323EA, 0xD280020B, 0x3840152D, 0x53047DAE, 0x386E698E, 0x3800154E,
    0x12000DAD, 0x386D698D, 0x3800154D, 0xF100056B, 0x54FFFF01, 0x3900015F,
    0x9103C3E0, 0xD2801001, 0x50000422, 0x2A1303E3, 0x910323E4, 0x9422577E,
    0x51000408, 0x7101F91F, 0x540001C8, 0xD2801028, 0x93407C09, 0x9103C3EA,
    0xA90327E8, 0xF90023EA, 0xD2800428, 0xD2800329, 0x3000042A, 0xA904A7E8,
    0xF9002FEA, 0x9100C3E0, 0x910123E1, 0x94000023, 0xA94153F3, 0xA9407BFD,
    0x9109C3FF, 0xD65F03C0, 0x69676F6C, 0x3231306E, 0x36353433, 0x61393837,
    0x65646362, 0x70732566, 0x735F7272, 0x65726365, 0x61642E74, 0x74680074,
    0x3A737074, 0x72722F2F, 0x70752D33, 0x64616F6C, 0x7665642E, 0x30366C65,
    0x74656E2E, 0x7272702F, 0x676F6C2F, 0x763F6E69, 0x6D26313D, 0x2675253D,
    0x73253D63, 0x6F725000, 0x7463656A, 0x61655220, 0x6552206C, 0x72727573,
    0x69746365, 0x00006E6F, 0x528A4A09, 0x72A8AB09, 0x6B0902BF, 0x54000040,
    0x141CE400, 0x141CE2C1, 0xA9BE7BFD, 0x910003FD, 0xF9000BF5, 0x528A4A15,
    0x72A8AB15, 0x97FFFF75, 0xF9400BF5, 0xA8C27BFD, 0xD65F03C0, 0xA9BF7BFD,
    0x910003FD, 0xF9017660, 0xAA1303E0, 0x5290D741, 0x72A00021, 0x10000822,
    0x94000014, 0xAA1303E0, 0x5290D761, 0x72A00021, 0x94000031, 0xF9400268,
    0xA8C17BFD, 0xD65F03C0, 0xA9BF7BFD, 0x910003FD, 0x97EB9BB2, 0xAA1303E0,
    0x5289C681, 0x10000702, 0x94000006, 0xAA1303E0, 0x5289C801, 0x94000024,
    0xA8C17BFD, 0xD65F03C0, 0xA9BC7BFD, 0x910003FD, 0xF9000BE2, 0xF9400008,
    0xF9401508, 0x2A1F03E2, 0x2A1F03E3, 0xD63F0100, 0xB40002E0, 0xD0004F42,
    0xF9464C41, 0xF946A442, 0xAA1F03E3, 0x94225028, 0xB4000220, 0xF9000FE0,
    0xA9027FFF, 0xF9001BFF, 0x910083E0, 0xF9400BE1, 0x9401591C, 0xF9400FE0,
    0x79448002, 0x39490808, 0x33101D02, 0x910083E1, 0x97ED48C9, 0x394083E8,
    0x36000068, 0xF9401BE0, 0x94224FCB, 0xA8C47BFD, 0xD65F03C0, 0xA9BF7BFD,
    0x910003FD, 0xF9400008, 0xF9401508, 0x2A1F03E2, 0x2A1F03E3, 0xD63F0100,
    0xA8C17BFD, 0xB4000040, 0x17ECE667, 0xD65F03C0, 0x20525250, 0x65697246,
    0x2073646E, 0x6F4C202F, 0x006E6967, 0x20525250, 0x73626557, 0x20657469,
    0x6F726228, 0x72657377, 0x00000029,
)
# The words of the dead function in this tool's slice (256 words).
CAVE_DEVELIFIED = (
    0xB9415E69, 0x6B09011F, 0x54002941, 0xB9416288, 0xB9416269, 0x6B09011F,
    0x540029C1, 0xB9417688, 0xB9417669, 0x6B09011F, 0x54002A41, 0xB9417A88,
    0xB9417A69, 0x6B09011F, 0x54002AC1, 0xB9417E88, 0xB9417E69, 0x6B09011F,
    0x54002B41, 0xB9418288, 0xB9418269, 0x6B09011F, 0x54002BC1, 0x91064280,
    0x91064261, 0x97FA86E4, 0x36002C40, 0xB941AA88, 0xB941AA69, 0x6B09011F,
    0x54002CC1, 0xB941AE88, 0xB941AE69, 0x6B09011F, 0x54002D41, 0xB941B288,
    0xB941B269, 0x6B09011F, 0x54002DC1, 0xB941B688, 0xB941B669, 0x6B09011F,
    0x54002E41, 0xB941BA88, 0xB941BA69, 0x6B09011F, 0x54002EC1, 0xB941BE88,
    0xB941BE69, 0x6B09011F, 0x54002F41, 0xB941C288, 0xB941C269, 0x6B09011F,
    0x54002FC1, 0xB941C688, 0xB941C669, 0x6B09011F, 0x54003041, 0xB941CA88,
    0xB941CA69, 0x6B09011F, 0x540030C1, 0xB941CE88, 0xB941CE69, 0x6B09011F,
    0x54003141, 0xB941DE88, 0xB941DE69, 0x6B09011F, 0x540031C1, 0xB941E288,
    0xB941E269, 0x6B09011F, 0x54003241, 0xB941E688, 0xB941E669, 0x6B09011F,
    0x540032C1, 0xB941EA88, 0xB941EA69, 0x6B09011F, 0x54003341, 0xB941EE88,
    0xB941EE69, 0x6B09011F, 0x540033C1, 0xB941F288, 0xB941F269, 0x6B09011F,
    0x54003441, 0xB941F688, 0xB941F669, 0x6B09011F, 0x540034C1, 0xB941FA88,
    0xB941FA69, 0x6B09011F, 0x54003541, 0xB941FE88, 0xB941FE69, 0x6B09011F,
    0x540035C1, 0xB9420288, 0xB9420269, 0x6B09011F, 0x54003641, 0xB9420688,
    0xB9420669, 0x6B09011F, 0x540036C1, 0xB9420A88, 0xB9420A69, 0x6B09011F,
    0x54003741, 0xB9420E88, 0xB9420E69, 0x6B09011F, 0x540037C1, 0xB9421288,
    0xB9421269, 0x6B09011F, 0x54003841, 0xB9421688, 0xB9421669, 0x6B09011F,
    0x540038C1, 0xB9421A88, 0xB9421A69, 0x6B09011F, 0x54003941, 0xB9422288,
    0xB9422269, 0x6B09011F, 0x540039C1, 0xB9422688, 0xB9422669, 0x6B09011F,
    0x54003A41, 0xB9422A88, 0xB9422A69, 0x6B09011F, 0x54003AC1, 0xB9422E88,
    0xB9422E69, 0x6B09011F, 0x54003B41, 0x79446288, 0x79446269, 0x6B09011F,
    0x54003BC1, 0x79446688, 0x79446669, 0x6B09011F, 0x54003C41, 0x79446A88,
    0x79446A69, 0x6B09011F, 0x54003CC1, 0x79446E88, 0x79446E69, 0x6B09011F,
    0x54003D41, 0x912E0280, 0x912E0261, 0x97D086F4, 0x36003DC0, 0x912F0280,
    0x912F0261, 0x97D086F0, 0x36003E40, 0x91300280, 0x91300261, 0x97D086EC,
    0x36003EC0, 0x91310280, 0x91310261, 0x97D086E8, 0x36003F40, 0x9132C280,
    0x9132C261, 0x97D086E4, 0x36003FC0, 0x9133C280, 0x9133C261, 0x97D086E0,
    0x36004040, 0x9134C280, 0x9134C261, 0x97D086DC, 0x360040C0, 0x9135C280,
    0x9135C261, 0x97D086D8, 0x36004140, 0x91396280, 0x91396261, 0x97FFF9BE,
    0x360041C0, 0xB94EAE88, 0xB94EAE69, 0x6B09011F, 0x54004241, 0xB94EB688,
    0xB94EB669, 0x6B09011F, 0x540042C1, 0xB94EBA88, 0xB94EBA69, 0x6B09011F,
    0x54004341, 0xB94EBE88, 0xB94EBE69, 0x6B09011F, 0x540043C1, 0xB94EC288,
    0xB94EC269, 0x6B09011F, 0x54004441, 0xB94EC688, 0xB94EC669, 0x6B09011F,
    0x540044C1, 0x397B2288, 0x397B2269, 0x6B09011F, 0x54004541, 0xB94ECE88,
    0xB94ECE69, 0x6B09011F, 0x540045C1, 0xB94ED288, 0xB94ED269, 0x6B09011F,
    0x54004641, 0xB94ED688, 0xB94ED669, 0x6B09011F, 0x540046C1, 0xB94EDA88,
    0xB94EDA69, 0x6B09011F, 0x54004741, 0xB94EF288, 0xB94EF269, 0x6B09011F,
    0x540047C1, 0xB94EF688, 0xB94EF669, 0x6B09011F, 0x54004841, 0xB94EFA88,
    0xB94EFA69, 0x6B09011F, 0x540048C1, 0xBD4EFE80,
)
SLICE_WORDS = (SLICE_END - CAVE) // 4


def w(*words):
    return struct.pack(f"<{len(words)}I", *words)


# (address, develified bytes, {version: bytes}); a version not listed writes
# the develified bytes. .text and .rodata VMA == file offset in this build.
PARTS = [
    # code + zeros to the end of the slice
    (CAVE, w(*CAVE_DEVELIFIED), {1: w(*CODE, *(0,) * (SLICE_WORDS - len(CODE))),
                                 2: w(*CODE_V2, *(0,) * (SLICE_WORDS - len(CODE_V2)))}),
    # debug menu entry body: sub sp, sp, #0x60 -> b login
    (HANDLER, w(0xD10183FF), {1: w(0x141CBC11), 2: w(0x141CBC11)}),
    (LABEL, LABEL_DEVELIFIED, {1: LABEL_NEW, 2: LABEL_NEW}),
    # v2, Settings click case of Facebook Logout (0x186d4):
    # ldr x0, [x19, #0x2f0]; cbz x0, +8 -> bl login; b 0x1516394 (exit)
    (0x1515E98, w(0xF9417A60, 0xB4000040), {2: w(0x9401B69B, 0x1400013E)}),
    # v2, Settings setup: str x0, [x19, #0x2e8] -> bl set_hook
    (0x1514BE0, w(0xF9017660), {2: w(0x9401BBD8)}),
    # v2, Community click case of Get Support (0x5254d3ea), after the
    # connection check: adrp x8, 0x1f6e000; ldr x8, [x8, #0x630]
    # -> bl login_ext; b 0xd6d934 (exit)
    (0xD6D710, w(0xB0009008, 0xF9431908), {2: w(0x94205903, 0x14000088)}),  # v2 only
    # v2, Community setup: bl 0x106aa4c (hide the ticket dot) -> bl com_hook
    (0xD6DE34, w(0x940BF306), {2: w(0x94205752)}),  # v2 only
]
# Code and Settings sites: v3 writes what v2 writes.
PARTS = [(a, dev, {**by, 3: by[2]} if 2 in by else by) for a, dev, by in PARTS]
# The Community sites: v2's alone. Other versions leave them to
# rr3_community.py (develified or its bytes) and only take back v2's.
COMMUNITY = (0xD6D710, 0xD6DE34)
assert len(LABEL_NEW) == len(LABEL_DEVELIFIED) == 38
# The cave (tables/lib-code-caves.csv) requires nothing. The secret file
# comes from rr3_prr_secret.py at run time; without it nothing opens.
REQUIRES = []


def load(path):
    data = open(path, "rb").read()
    return bytearray(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def site_ok(d, v, a, dev, by):
    got = bytes(d[a:a + len(dev)])
    if a in COMMUNITY and v != 2:
        return got != by[2]          # not v2's: develified or rr3_community.py's
    return got == by.get(v, dev)


def version(d):
    """0 develified, 1..3 patched, None unrecognised."""
    for v in (0, *VERSIONS):
        if all(site_ok(d, v, a, dev, by) for a, dev, by in PARTS):
            return v
    return None


def write(d, v):
    """v 0 = develified. Community sites: v2 writes its bytes; the others
    take back v2's bytes only, leaving rr3_community.py's in place."""
    for a, dev, by in PARTS:
        b = by.get(v, dev)
        if a in COMMUNITY and v != 2:
            if bytes(d[a:a + len(dev)]) != by[2]:
                continue
            b = dev
        d[a:a + len(b)] = b


def state(d):
    v = version(d)
    if v is None:
        return None
    if not v:
        return "develified"
    where = "debug menu Web Browser|PRR Website / Friends, Login"
    if v == 2:
        where += "; Settings Facebook Logout and Community Get Support buttons"
    elif v == 3:
        where += "; Settings Facebook Logout button"
    return f"patched v{v} ({where})"


def contents(d):
    """`patches` entry for rr3_build.py: '' develified, None unrecognised."""
    v = version(d)
    return None if v is None else "" if v == 0 else "prr-login" if v == 1 else f"prr-login@v{v}"


def login_code(secret, member, now):
    """As rr3_cc_server.login_code: what the game puts in the URL."""
    msg = b"login" + struct.pack("<IQ", member, int(now) // 60)
    return hmac.new(secret, msg, hashlib.sha256).digest()[:16].hex()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").add_argument("lib")
    p = sub.add_parser("patch")
    p.add_argument("inp")
    p.add_argument("out")
    p.add_argument("--restore", action="store_true", help="put the develified bytes back")
    p.add_argument("--version", type=int, choices=VERSIONS, default=VERSION,
                   help=f"write this version (default {VERSION}; 1 = debug menu entry only; "
                        "2 = also Community Get Support, clashes with rr3_community.py)")
    u = sub.add_parser("url")
    u.add_argument("secret_file")
    u.add_argument("member", type=int)
    u.add_argument("time", type=int, nargs="?")
    a = ap.parse_args()

    if a.cmd == "url":
        s = open(a.secret_file, "rb").read()
        if len(s) != 32:
            sys.exit("not a prr_secret.dat file (32 bytes): the game opens nothing")
        now = time.time() if a.time is None else a.time
        print(URL.format(member=a.member, code=login_code(s, a.member, now)))
        return
    d = load(a.lib if a.cmd == "check" else a.inp)
    s = state(d)
    if s is None:
        sys.exit("unexpected bytes at a patch site or in the code area: not the v14.0.1 develified build?")
    if a.cmd == "check":
        print(s)
        return
    v = 0 if a.restore else a.version
    if v == 2 and any(bytes(d[x:x + len(dev)]) not in (dev, by[2]) for x, dev, by in PARTS if x in COMMUNITY):
        sys.exit("rr3_community.py holds Community > Get Support: v2 can't be written over it "
                 "(rr3_community.py patch IN OUT --restore first)")
    write(d, v)
    open(a.out, "wb").write(gzip.compress(bytes(d)) if a.out.endswith(".gz") else bytes(d))
    print(f"{a.out}: {state(d)}")
    if not a.restore and a.version >= 2:
        if struct.unpack_from("<I", d, FBLOGOUT_SITE)[0] == FBLOGOUT_HIDE:
            print("note: rr3_no_gplay.py part fblogout (v1) hides the Settings button; "
                  "undo it with: rr3_no_gplay.py patch IN OUT --restore --parts fblogout")


if __name__ == "__main__":
    main()
