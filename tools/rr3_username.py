#!/usr/bin/env python3
"""Leaderboard username from the ENTER RACING CODE button (issue #82), by
patching libRealRacing3.so (v14.0.1, arm64, develified build). Version 5
(v4 + the player's own name in game, issue #156), confirmed in game
(b50, 2026-11-03).
Version 4 (v3 + the Settings button text, issue #162) and version 3
(issue #104) confirmed in game (b48, 2026-11-02). v1 and v2 confirmed in
game (b28 and b28 + v2, 2026-10-19).
Guide: docs/leaderboard-username.md.

The button keeps opening the game's text-entry popup, but the typed text goes
to our code instead of the promo-code handler. Our code keeps the name in its
own file, files/doc/leaderboard_username.dat, and adds it to every leaderboard
request so tools/rr3_cc_server.py can show it. A new name is sent from the
next game start.

  0x1516438  ENTER RACING CODE (event 0x51f1bc4c) builds a std::function for
  0x151643c  the popup: `adrp x9 ; ldr x9, [x9, #0xe38]` (promo handler
             0x1516b1c from the GOT) -> `adrp x9 ; add x9, x9, #0x490`
             (name_set 0xe2f490). Called as name_set(screen, text).
  0x1d04b80  Cloudcell request header writer 0x1d04438, before the auth
             block: `ldr x0, [x25]` -> `b 0xe2f5b0` (name_hdr). If the file
             holds a name, the header gets one more string "rrname:<name>".
             With no name the header is unchanged.
  0x151646c  v2: the popup's keyboard flags (popup 0x1511ed8: w5 uppercase only,
             w6 letters and digits only, w7 password). The promo popup sets
             `mov w7, #1` -> `mov w7, #0`. With the password flag the Java
             keyboard (MainActivity.showKeyboardInput, CheatView) is a
             password field and deletes everything but letters, digits and
             spaces, so `-` could not be typed (v1, 2026-10-19).
  0xe2f490   new code (v1/v2 572 bytes, v3 568, tools/asm/rr3_username.s) in
             SetupSaleCheats after rr3_debug_menu.py `settings` and `trim`.
             Needs rr3_debug_menu.py part `nosales` (issue #84), which makes
             SetupSaleCheats unreachable.
  v3 (issue #104):
  0xee962c   the text-entry popup's check (0xee94f4, run on every text
             change), start of its empty/all-space test: `ldrb w8, [x20]`
             -> `b 0x109b634` (chk). For our popup (callback target
             name_set) the test is our name rules, so the red "Invalid
             username" line and a refused confirm follow them. Other
             popups keep the develified test.
  0x109b634  chk + the title string (123 of 144 bytes; a dead file loader,
             no callers).
  0x1516440  popup title: the heading key `GAMETEXT_PROMO_ENTRY_HEADING`
  0x151644c  -> our string "Change username (restart required)" (the text
             lookup returns a non-key as it is).
  0xeaf8fc   Race Teams team tag popup `mov w7, #1` -> `mov w7, #0`: the
             Java keyboard takes the password flag from the first popup of
             a game start (#110), so this one must not set it either.
  v4 (issue #162), everything of v3 plus:
  0x1514b54  Settings screen widget setup (0x1514a64): `str x0, [x19, #0x2a8]`
             (keeps the ENTER RACING CODE button) -> `bl 0x1ac0be8` (btn).
             btn runs that store, finds the button's label (id 0x51f1bc4d),
             checks it is a GuiLabel and sets its text to the v3 title
             string; the label's forceUppercase shows it as
             "CHANGE USERNAME (RESTART REQUIRED)".
  0x1ac0be8  btn, in two free parts of the .text zero padding (88 + 68
  0x1ac0fac  bytes, tables/lib-code-caves.csv).
  v5 (issue #156), everything of v4 plus:
  0x1caf450  cc::social::MemberManager vfunc 0x30, the player's display name
             getter (analysis/leaderboard-username.md section 10): first
             instruction `sub sp, sp, #0x70` -> `b 0x1584350` (name_get).
             With a name in the file the getter returns it; without one
             the game's getter runs ("Guest" offline, "prr:NNNN" online
             with rr3_prr_social.py).
  0x1584350  name_get, this tool's slice 0x1584350..0x1584450 of the dead
             physics-state compare (tables/lib-code-caves.csv); code + zeros.

Name rules (v3, name_ok, used by name_set and chk): spaces at both ends are
dropped; 3..16 characters of A-Z a-z 0-9 _ - . ! ? ~ + * # are saved;
anything else (empty text too) is ignored and the old name kept.
v1/v2: A-Z a-z 0-9 _ - . only, and empty text saved "no name".

File format (little-endian, 28 bytes): "RRUN", version 1, name length
(0 = none), name (16 bytes, zero padded).

Usage:
  rr3_username.py check LIB
  rr3_username.py patch IN OUT [--version 1|2|3|4|5] [--restore]
  rr3_username.py show FILE         (a leaderboard_username.dat)
  rr3_username.py write FILE NAME   (make one, e.g. for a test; "" = no name)
IN may be gzipped; OUT is written uncompressed (or gzipped if it ends in .gz).
"""
import argparse
import gzip
import re
import struct
import sys

VERSION = 5
CAVE = 0xE2F490
# tools/asm/rr3_username.s linked for 0xe2f490 (build line in that file), v3.
CODE = (
    0xA9AC7BFD, 0x910003FD, 0xA901FFFF, 0xA902FFFF, 0xB4000401, 0xAA0103E0,
    0x9400005E, 0x340003A0, 0x910093EE, 0xD280000D, 0x386D692A, 0x382D69CA,
    0x910005AD, 0xEB0C01BF, 0x54FFFF83, 0x528A4A48, 0x72A9CAA8, 0xB9001BE8,
    0x52800028, 0xB9001FE8, 0xB90023EC, 0x910103E0, 0x94000043, 0x910103E0,
    0xB0FFAEA1, 0x91336821, 0x943FA1FA, 0xB4000120, 0xF9000BE0, 0xAA0003E3,
    0x910063E0, 0xD2800021, 0xD2800382, 0x943FA21B, 0xF9400BE0, 0x943FA1F5,
    0xA8D47BFD, 0xD65F03C0, 0xA9AC7BFD, 0x910003FD, 0x910103E0, 0x94000030,
    0x910103E0, 0xF0FFAFE1, 0x911FF821, 0x943FA1E7, 0xB4000500, 0xF9000BE0,
    0xAA0003E3, 0x910063E0, 0xD2800021, 0xD2800382, 0x943FA250, 0xF9001FE0,
    0xF9400BE0, 0x943FA1E1, 0xF9401FE0, 0xF100701F, 0x54000381, 0xB9401BE8,
    0x528A4A49, 0x72A9CAA9, 0x6B09011F, 0x540002E1, 0xB9401FE8, 0x7100051F,
    0x5400028B, 0xB94023E8, 0x71000D1F, 0x54000223, 0x7100411F, 0x540001E8,
    0x11001D08, 0xB90037E8, 0xAA1303E0, 0x9100D3E1, 0x52800082, 0x943A39D9,
    0xAA1303E0, 0x10000641, 0x528000E2, 0x943A39D5, 0xAA1303E0, 0x910093E1,
    0xB94023E2, 0x943A39D1, 0xA8D47BFD, 0xF9400320, 0x143B5565, 0xA9BE7BFD,
    0x910003FD, 0xF9000BE0, 0x9411D87C, 0xAA0003E3, 0xF9400BE0, 0xD2802001,
    0x70000442, 0x943FA887, 0xA8C27BFD, 0xD65F03C0, 0x100004CE, 0xA94041CF,
    0xAA0003E9, 0x3840140A, 0x7100815F, 0x54FFFFA0, 0xAA0903EB, 0x340001EA,
    0x7100815F, 0x54000160, 0xD100040D, 0xEB0B01BF, 0x540001E1, 0x7101FD5F,
    0x540001A8, 0x721A015F, 0x9A9001EE, 0x9ACA25CE, 0x3600012E, 0xAA0003EB,
    0x3840140A, 0x17FFFFF2, 0xCB09016C, 0xD1000D8D, 0xF10035BF, 0x1A9F87E0,
    0xD65F03C0, 0x52800000, 0xD65F03C0, 0x616E7272, 0x253A656D, 0x61656C73,
    0x62726564, 0x6472616F, 0x6573755F, 0x6D616E72, 0x61642E65, 0x00000074,
    0x00000000, 0x83FF6C0A, 0x87FFFFFE, 0x47FFFFFE,
)
NAME_SET, NAME_HDR, NAME_OK = 0xE2F490, 0xE2F528, 0xE2F620
CHK = 0x109B634
# .cave2 of tools/asm/rr3_username.s linked for 0x109b634: chk + title.
CHK_CODE = (
    0xF941F269, 0xB4000269, 0xF940052A, 0x90FFECAB, 0x9112416B, 0xEB0B015F,
    0x540001C1, 0xF940012A, 0xF00076EB, 0xF947196B, 0x9100416B, 0xEB0B015F,
    0x54000101, 0x39400288, 0x91000680, 0x36000048, 0xF9400A80, 0x97F64FEA,
    0x0A0002B5, 0x17F93815, 0x39400288, 0x17F937EA, 0x6E616843, 0x75206567,
    0x6E726573, 0x20656D61, 0x73657228, 0x74726174, 0x71657220, 0x65726975,
    0x00002964,
)
TITLE = 0x109B68C
BTN = 0x1AC0BE8
BTN2 = 0x1AC0FAC
# .cave3 / .cave4 of tools/asm/rr3_username.s (v4): btn, split over two
# free parts of the zero padding (develified bytes there are zero).
BTN_CODE = (
    0xA9BD7BFD, 0x910003FD, 0xF9015660, 0xF9400268, 0xF9401508, 0xAA1303E0,
    0x529789A1, 0x72AA3E21, 0x2A1F03E2, 0x2A1F03E3, 0xD63F0100, 0xB4001E80,
    0xB0002562, 0xF9464C41, 0xF946A442, 0xAA1F03E3, 0x940D5C16, 0xB4001DC0,
    0xF9000BE0, 0xA901FFFF, 0xF90017FF, 0x140000DC,
)
BTN2_CODE = (
    0x910063E0, 0xF0FFAEC1, 0x911A3021, 0x97EC642D, 0xF9400BE0, 0x79448002,
    0x39490808, 0x33101D02, 0x910063E1, 0x97D853DA, 0x394063E8, 0x36000068,
    0xF94017E0, 0x940D5ADC, 0xF9400268, 0xA8C37BFD, 0xD65F03C0,
)
GETTER, GETTER_SLICE = 0x1CAF450, 0x1584350
# .cave5 of tools/asm/rr3_username.s (v5): name_get.
GET_CODE = (
    0xA9AB7BFD, 0x910003FD, 0xA90123E0, 0x910143E0, 0x97E2ACA5, 0x910143E0,
    0xD0FF7541, 0x911FF821, 0x94224E5C, 0xB4000500, 0xF90013E0, 0xAA0003E3,
    0x9100C3E0, 0xD2800021, 0xD2800382, 0x94224EC5, 0xF90017E0, 0xF94013E0,
    0x94224E56, 0xF94017E0, 0xF100701F, 0x54000381, 0xB94033E8, 0x528A4A49,
    0x72A9CAA9, 0x6B09011F, 0x540002E1, 0xB94037E8, 0x7100051F, 0x5400028B,
    0xB9403BE8, 0x51000D09, 0x7100353F, 0x54000208, 0xF9400FEA, 0xA9007D5F,
    0xF900095F, 0x531F7909, 0x39000149, 0x9100F3EB, 0xD280000C, 0x386C6969,
    0x8B0C014D, 0x390005A9, 0x9100058C, 0xEB08019F, 0x54FFFF63, 0xA8D57BFD,
    0xD65F03C0, 0xA94123E0, 0xA8D57BFD, 0xD101C3FF, 0x141CAC0D,
)
# The dead physics-state compare's words in the slice 0x1584350..0x1584450.
GET_DEVELIFIED = (
    0x3707C280, 0xB0FF73E0, 0x912E5400, 0x97EC6DAF, 0x2A1F03F5, 0x912F0280,
    0x912F0261, 0x97D084FF, 0x3707C200, 0xB0FF73E0, 0x912E5400, 0x97EC6DA7,
    0x2A1F03F5, 0x91300280, 0x91300261, 0x97D084F7, 0x3707C180, 0xB0FF73E0,
    0x912E5400, 0x97EC6D9F, 0x2A1F03F5, 0x91310280, 0x91310261, 0x97D084EF,
    0x3707C100, 0xB0FF73E0, 0x912E5400, 0x97EC6D97, 0x2A1F03F5, 0x9132C280,
    0x9132C261, 0x97D084E7, 0x3707C080, 0xF0FF7800, 0x91269C00, 0x97EC6D8F,
    0x2A1F03F5, 0x9133C280, 0x9133C261, 0x97D084DF, 0x3707C000, 0xF0FF7800,
    0x91269C00, 0x97EC6D87, 0x2A1F03F5, 0x9134C280, 0x9134C261, 0x97D084D7,
    0x3707BF80, 0xF0FF7800, 0x91269C00, 0x97EC6D7F, 0x2A1F03F5, 0x9135C280,
    0x9135C261, 0x97D084CF, 0x3707BF00, 0xF0FF7800, 0x91269C00, 0x97EC6D77,
    0x2A1F03F5, 0x91396280, 0x91396261, 0x97FFF7B1,
)
# The dead loader's words CHK_CODE replaces.
CHK_DEVELIFIED = (
    0xD10103FF, 0xA9017BFD, 0xF90013F5, 0xA9034FF4, 0x910043FD, 0xD53BD055,
    0xF94016A8, 0x910013E1, 0x52800022, 0x52800023, 0xF90007E8, 0xB90007FF,
    0x94088500, 0xB4000220, 0xB94007E1, 0xAA0003F4, 0x97FFFE3F, 0x2A0003F3,
    0xAA1403E0, 0x9435F1AC, 0xF94016A8, 0xF94007E9, 0xEB09011F, 0x54000181,
    0x2A1303E0, 0xA9434FF4, 0xF94013F5, 0xA9417BFD, 0x910103FF, 0xD65F03C0,
    0x12800013,
)
# v1/v2 code at 0xe2f490 (name_hdr at 0xe2f5b0), still recognised by `check`.
CODE_V2 = (
    0xA9AC7BFD, 0x910003FD, 0xA901FFFF, 0xA902FFFF, 0xB4000841, 0xAA0103E9,
    0x3940012A, 0x7100815F, 0x54000061, 0x91000529, 0x17FFFFFC, 0xAA0903EB,
    0x3940016A, 0x3400006A, 0x9100056B, 0x17FFFFFD, 0xEB09017F, 0x540000C9,
    0x385FF16A, 0x7100815F, 0x54000061, 0xD100056B, 0x17FFFFFA, 0xCB09016C,
    0xB400032C, 0xF1000D9F, 0x54000583, 0xF100419F, 0x54000548, 0xD280000D,
    0x386D692A, 0x5100C14E, 0x710025DF, 0x54000169, 0x321B014E, 0x510185CE,
    0x710065DF, 0x540000E9, 0x71017D5F, 0x540000A0, 0x7100B55F, 0x54000060,
    0x7100B95F, 0x54000361, 0x910093EE, 0x382D69CA, 0x910005AD, 0xEB0C01BF,
    0x54FFFDC3, 0x528A4A48, 0x72A9CAA8, 0xB9001BE8, 0x52800028, 0xB9001FE8,
    0xB90023EC, 0x910103E0, 0x94000043, 0x910103E0, 0xB0FFAEA1, 0x91336821,
    0x943FA1D8, 0xB4000120, 0xF9000BE0, 0xAA0003E3, 0x910063E0, 0xD2800021,
    0xD2800382, 0x943FA1F9, 0xF9400BE0, 0x943FA1D3, 0xA8D47BFD, 0xD65F03C0,
    0xA9AC7BFD, 0x910003FD, 0x910103E0, 0x94000030, 0x910103E0, 0xF0FFAFE1,
    0x911FF821, 0x943FA1C5, 0xB4000500, 0xF9000BE0, 0xAA0003E3, 0x910063E0,
    0xD2800021, 0xD2800382, 0x943FA22E, 0xF9001FE0, 0xF9400BE0, 0x943FA1BF,
    0xF9401FE0, 0xF100701F, 0x54000381, 0xB9401BE8, 0x528A4A49, 0x72A9CAA9,
    0x6B09011F, 0x540002E1, 0xB9401FE8, 0x7100051F, 0x5400028B, 0xB94023E8,
    0x71000D1F, 0x54000223, 0x7100411F, 0x540001E8, 0x11001D08, 0xB90037E8,
    0xAA1303E0, 0x9100D3E1, 0x52800082, 0x943A39B7, 0xAA1303E0, 0x100002A1,
    0x528000E2, 0x943A39B3, 0xAA1303E0, 0x910093E1, 0xB94023E2, 0x943A39AF,
    0xA8D47BFD, 0xF9400320, 0x143B5543, 0xA9BE7BFD, 0x910003FD, 0xF9000BE0,
    0x9411D85A, 0xAA0003E3, 0xF9400BE0, 0xD2802001, 0x700000A2, 0x943FA865,
    0xA8C27BFD, 0xD65F03C0, 0x616E7272, 0x253A656D, 0x61656C73, 0x62726564,
    0x6472616F, 0x6573755F, 0x6D616E72, 0x61642E65, 0x00000074,
)
# The SetupSaleCheats words CODE replaces.
CODE_DEVELIFIED = (
    0x927CED17, 0xAA1703E0, 0x943FA1AA, 0xAA0003F6, 0xB24002E8, 0xA90083F4,
    0xF90003E8, 0xB40000B4, 0xAA1603E0, 0xAA1503E1, 0xAA1403E2, 0x943FA1D1,
    0xB0FFAD21, 0x9100B021, 0x910003E0, 0x52800302, 0x38346ADF, 0x941E8762,
    0xD0008268, 0xD000826A, 0x9109E108, 0xD10103A9, 0x910BE14A, 0x9100C3F4,
    0x910003E1, 0xD10103A2, 0x9100C3E3, 0xAA1303E0, 0xA93C4FA8, 0xF81E03A9,
    0xF9001BEA, 0xF9002BF4, 0x9400013A, 0xF9402BE0, 0xEB00029F, 0x540000A0,
    0xB40000E0, 0xF9400008, 0xF9401508, 0x14000003, 0xF9400008, 0xF9401108,
    0xD63F0100, 0xF85E03A0, 0xD10103A8, 0xEB00011F, 0x540000A0, 0xB40000E0,
    0xF9400008, 0xF9401508, 0x14000003, 0xF9400008, 0xF9401108, 0xD63F0100,
    0x394003E8, 0x36000068, 0xF9400BE0, 0x943FA177, 0x394063E8, 0xA9422BE9,
    0xA9007FFF, 0xF9000BFF, 0xD341FD0B, 0x7200011F, 0x9A890174, 0x91004688,
    0x9A8A0335, 0xB100411F, 0x54000B22, 0xF1005D1F, 0x540000E2, 0x910003E9,
    0x531F7A88, 0xB2400136, 0x390003E8, 0xB5000154, 0x1400000D, 0x91008688,
    0x927CED17, 0xAA1703E0, 0x943FA15C, 0xB24002E8, 0xAA0003F6, 0xA90083F4,
    0xF90003E8, 0xAA1603E0, 0xAA1503E1, 0xAA1403E2, 0x943FA184, 0xB0FFABC1,
    0x913B7021, 0x910003E0, 0x52800222, 0x38346ADF, 0x941E8715, 0xD0008268,
    0xD000826A, 0x910DE108, 0xD10103A9, 0x910FE14A, 0x9100C3F4, 0x910003E1,
    0xD10103A2, 0x9100C3E3, 0xAA1303E0, 0xA93C4FA8, 0xF81E03A9, 0xF9001BEA,
    0xF9002BF4, 0x940000ED, 0xF9402BE0, 0xEB00029F, 0x540000A0, 0xB40000E0,
    0xF9400008, 0xF9401508, 0x14000003, 0xF9400008, 0xF9401108, 0xD63F0100,
    0xF85E03A0, 0xD10103A8, 0xEB00011F, 0x540000A0, 0xB40000E0, 0xF9400008,
    0xF9401508, 0x14000003, 0xF9400008, 0xF9401108, 0xD63F0100, 0x394003E8,
    0x370001C8, 0x394063E8, 0x37000208, 0xF9401708, 0xF85F83A9, 0xEB09011F,
    0x54000241, 0xA94E4FF4, 0xA94D57F6, 0xA94C5FF8, 0xF9405BF9,
)
# (address, develified words, {version: words}); a version not listed writes
# the develified words. .text VMA == file offset in this build.
V3UP = (3, 4, 5)  # versions with everything of v3
PARTS = [
    (CAVE, CODE_DEVELIFIED, {1: CODE_V2, 2: CODE_V2, **{v: CODE + CODE_DEVELIFIED[len(CODE):] for v in V3UP}}),
    # promo handler -> name_set (std::function target at 0x1516438)
    (0x1516438, (0x90005329, 0xF9471D29), {v: (0xB0FFC8C9, 0x91124129) for v in (1, 2, *V3UP)}),
    # ldr x0, [x25] -> b name_hdr (0xe2f5b0 in v1/v2, 0xe2f528 from v3)
    (0x1D04B80, (0xF9400320,), {1: (0x17C4AA8C,), 2: (0x17C4AA8C,), **{v: (0x17C4AA6A,) for v in V3UP}}),
    # v2: keyboard without the password flag (lets `-`, `_`, `.` be typed)
    (0x151646C, (0x52800027,), {v: (0x52800007,) for v in (2, *V3UP)}),  # mov w7, #1 -> #0
    # v3: popup title: adrp x0, 0x498000 / add x0, x0, #0x11b -> TITLE
    (0x1516440, (0xD0FF7C00,), {v: (0xB0FFDC20,) for v in V3UP}),
    (0x151644C, (0x91046C00,), {v: (0x911A3000,) for v in V3UP}),
    # v3: popup check: ldrb w8, [x20] -> b chk
    (0xEE962C, (0x39400288,), {v: (0x1406C802,) for v in V3UP}),
    (CHK, CHK_DEVELIFIED, {v: CHK_CODE + CHK_DEVELIFIED[len(CHK_CODE):] for v in V3UP}),
    # v3: team tag popup without the password flag (#110): mov w7, #1 -> #0
    (0xEAF8FC, (0x52800027,), {v: (0x52800007,) for v in V3UP}),
    # v4: Settings button text: str x0, [x19, #0x2a8] -> bl btn
    (0x1514B54, (0xF9015660,), {v: (0x9416B025,) for v in (4, 5)}),
    (BTN, (0,) * len(BTN_CODE), {v: BTN_CODE for v in (4, 5)}),
    (BTN2, (0,) * len(BTN2_CODE), {v: BTN2_CODE for v in (4, 5)}),
    # v5: name getter: sub sp, sp, #0x70 -> b name_get
    (GETTER, (0xD101C3FF,), {5: (0x17E353C0,)}),
    (GETTER_SLICE, GET_DEVELIFIED, {5: GET_CODE + (0,) * (len(GET_DEVELIFIED) - len(GET_CODE))}),
]
NOSALES = (0xE278C0, 0xD503201F)  # rr3_debug_menu.py part nosales: bl 0xe2f2b4 -> nop
# Code caves this tool writes in need these (tables/lib-code-caves.csv,
# checked by rr3_patch_sites.py check); `patch` refuses a lib without them.
# The v5 slice's cave (0x1583704) requires nothing.
REQUIRES = ["rr3_debug_menu.py nosales"]
NAME_RE = re.compile(r"[A-Za-z0-9_.!?~+*#-]{3,16}")
NAME_RE_V2 = re.compile(r"[A-Za-z0-9_.-]{3,16}")


def load(path):
    data = open(path, "rb").read()
    return bytearray(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def words(part, v):
    addr, develified, by_version = part
    return by_version.get(v, develified)


def version(d):
    """0 develified, 1..5 patched, None unrecognised."""
    have = [struct.unpack_from(f"<{len(p[1])}I", d, p[0]) for p in PARTS]
    for v in (0, 1, 2, 3, 4, 5):
        if all(h == words(p, v) for h, p in zip(have, PARTS)):
            return v
    return None


def state(d):
    v = version(d)
    if v is None:
        return None
    return f"patched v{v} (leaderboard username from ENTER RACING CODE)" if v else "develified"


def contents(d):
    """`patches` entry for rr3_build.py: '' develified, None unrecognised."""
    v = version(d)
    return None if v is None else "" if v == 0 else "username" if v == 1 else f"username@v{v}"


def problems(d):
    """For rr3_build.py: the code is in but nosales is not (the menu would run it)."""
    if version(d) and struct.unpack_from("<I", d, NOSALES[0])[0] != NOSALES[1]:
        return ["username code without rr3_debug_menu.py part nosales: the debug menu would run it"]
    return []


def record(name):
    if name and not NAME_RE.fullmatch(name):
        sys.exit("name must be 3..16 characters of A-Z a-z 0-9 _ - . ! ? ~ + * #")
    return b"RRUN" + struct.pack("<II", 1, len(name)) + name.encode().ljust(16, b"\0")


def show(path):
    b = open(path, "rb").read()
    if len(b) != 28 or b[:4] != b"RRUN":
        sys.exit("not a leaderboard_username.dat file")
    ver, n = struct.unpack_from("<II", b, 4)
    name = b[12:12 + n].decode("ascii", "replace") if 3 <= n <= 16 else ""
    print(f"version {ver}, name: {name or '(none: Racer NNNN)'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").add_argument("lib")
    p = sub.add_parser("patch")
    p.add_argument("inp")
    p.add_argument("out")
    p.add_argument("--version", type=int, choices=(1, 2, 3, 4, 5), default=VERSION,
                   help=f"patch version to write (default {VERSION}); 4: in-game name stays the game's; 3: Settings button keeps "
                        "ENTER RACING CODE; 2: no name check in the "
                        "popup, old rules; 1: also keeps the password keyboard")
    p.add_argument("--restore", action="store_true", help="put the develified bytes back")
    sub.add_parser("show").add_argument("file")
    w = sub.add_parser("write")
    w.add_argument("file")
    w.add_argument("name")
    a = ap.parse_args()

    if a.cmd == "show":
        show(a.file)
        return
    if a.cmd == "write":
        open(a.file, "wb").write(record(a.name.strip()))
        show(a.file)
        return
    d = load(a.lib if a.cmd == "check" else a.inp)
    s = state(d)
    if s is None:
        sys.exit("unexpected bytes at a patch site or in the code area: not the v14.0.1 develified build?")
    if a.cmd == "check":
        print(s)
        return
    if not a.restore and struct.unpack_from("<I", d, NOSALES[0])[0] != NOSALES[1]:
        sys.exit("needs rr3_debug_menu.py part nosales first (the new code goes in SetupSaleCheats)")
    for p in PARTS:
        w = words(p, 0 if a.restore else a.version)
        struct.pack_into(f"<{len(w)}I", d, p[0], *w)
    open(a.out, "wb").write(gzip.compress(bytes(d)) if a.out.endswith(".gz") else bytes(d))
    print(f"{a.out}: {state(d)}")


if __name__ == "__main__":
    main()
