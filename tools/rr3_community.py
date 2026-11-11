#!/usr/bin/env python3
"""Community screen: our links and labels (issue #145), by patching
libRealRacing3.so (v14.0.1, arm64, develified build). Version 2, untested
in game (v1 is in b54-stable, untested in game). Guide: docs/community-screen.md.

Part of Project Real Resurrection's work on Real Racing 3. Not affiliated
with, endorsed or supported by Electronic Arts.

Decided by Tom (2026-11-09). Every link opens in the phone's browser
(0x1cbc61c), not logged in, after the screen's own connection check:

  Button (widget id)                 Label                         Link
  Like us on Facebook (0x4e3a)       Join the Facebook community   https://www.facebook.com/share/g/1KJpECnfwj/
  Get Support (0x5254d3ea)           Real Racing 3 on Reddit       https://www.reddit.com/r/RealRacing3/
  Invite Facebook Friends (0x4e3d)   v2: Party Play                 opens the Party Play screen
                                     (v1: hidden, unused)
  Follow us on Twitter (0x4e43)      unchanged                     https://x.com/RR3PR3official
  Subscribe to our YouTube (0x4e45)  unchanged                     https://www.youtube.com/@ProjectRessurection-3
  Follow us on Instagram (0x5fd172e8) Join our Discord             https://discord.gg/project-resurrection-official-server-1482888689854971997
  Visit the R3 Website (0x5fd172f0)  Visit the PRR website         https://prr3.devel60.net/

The EA Help logo above Get Support (0x4e40) is hidden. Logos are game data:
the Discord logo over the Instagram button is left for later.

v2 (#145/#126, Tom 2026-11-09): Invite Facebook Friends is shown again as
"Party Play" and opens PartyPlayLocalScreen, as the community
Party_Play.apk does from the main menu (0xf1d698):
ScreenManager::OpenScreen(this->+0x158, "PartyPlayLocalScreen"), 0x14a7f90,
name 0x404c10. No connection check (Party Play is local). A race still needs
2 game controllers, or the debug menu's Party Play > Force 2 Players.
Labels are English in every language (the layout upper-cases them).

All in place, in the Community click handler (0xd6d2a4) and its setup
(0xd6ddac), no code cave (tools/asm/rr3_community.s):

  0xd6d350 / 0xd6d44c / 0xd6d578 / 0xd6d644 / 0xd6d748
             the five link cases, right after their connection check:
             EA's server-variable lookup -> std::string over our URL,
             bl 0x1cbc61c, b exit (0xd6d934); the URL follows the code.
  0xd6d710   Get Support, after its check: the EA Help code -> the same,
             Reddit URL at 0xd6d960 (EA Help code this case used to
             branch to, reached from nowhere else).
  0xd6d510   v2: Invite's case, from its first instruction (5 words):
             ldr x0, [x19, #0x158]; adrp/add x1, "PartyPlayLocalScreen";
             bl 0x14a7f90; b exit. The rest of the case is unreached.
  0xd6db3c   com_hook + relabel + hide + the label texts, in the same
             unreached EA Help code (0xd6db3c..0xd6dcec); v2 relabels
             Invite's label 0x4e3e instead of hiding the button.
  0xd6de34   setup: bl 0x106aa4c (hides the support ticket dot)
             -> bl com_hook (same call, then labels and hides).

Get Support and the setup call were rr3_prr_login.py v2's (Get Support =
PRR website): use rr3_prr_login.py v3, which leaves them to this tool.
`check` reports a lib with prr-login v2 as not patched by this tool.

Usage:
  rr3_community.py check LIB
  rr3_community.py patch IN OUT [--version N] [--restore]
IN may be gzipped; OUT is written uncompressed (or gzipped if it ends in .gz).
"""
import argparse
import gzip
import struct
import sys

VERSION = 2
VERSIONS = (1, 2)
REQUIRES = []                         # no code cave
EXIT = 0xD6D934
URLS = {
    "fb": "https://www.facebook.com/share/g/1KJpECnfwj/",
    "web": "https://prr3.devel60.net/",
    "tw": "https://x.com/RR3PR3official",
    "yt": "https://www.youtube.com/@ProjectRessurection-3",
    "sup": "https://www.reddit.com/r/RealRacing3/",
    "dc": "https://discord.gg/project-resurrection-official-server-1482888689854971997",
}
LABELS = {0x4E32: "Join the Facebook community", 0x4E34: "Real Racing 3 on Reddit",
          0x5FD17249: "Join our Discord", 0x5FD1724C: "Visit the PRR website"}
LABELS_V2 = {**LABELS, 0x4E3E: "Party Play"}  # Invite's label
HIDDEN = (0x4E40, 0x4E3D)             # v1: EA Help logo, Invite Facebook Friends
HIDDEN_V2 = (0x4E40,)                 # v2: EA Help logo only
OPEN_SCREEN, PP_NAME = 0x14A7F90, 0x404C10   # "PartyPlayLocalScreen"
# rr3_prr_login.py v2's words at two of these sites (Get Support = PRR website).
PRR_LOGIN_V2 = {0xD6D710: (0x94205903, 0x14000088), 0xD6DE34: (0x94205752,)}

# tools/asm/rr3_community.s linked as its build line says:
# (address, name, develified words, {version: words}). A version's words
# shorter than the develified ones leave the rest develified; a part a
# version doesn't list stays develified.
PARTS = [
    # Like us on Facebook (0x4e3a) case 0xd6d344, after its check
    (0xD6D350, "fb", (
        0xD0FFB5C8, 0x91258D08, 0x3DC00100, 0xF840D108, 0x52800549, 0x52800600,
        0xA9377FBF, 0xF81803BF, 0x381583A9, 0x3C881300, 0xF808E308, 0x3816E3BF,
        0x9442A9F0, 0x90FFB0E8, 0x3DC34100, 0xB0FFB2A8, 0x91101908, 0xF81503A0,
        0x3C9403A0, 0xAD400500,
    ), {
        1: (
            0x10000109, 0xD2800628, 0xD280058A, 0xA9372BA8, 0xF81803A9, 0xD10243A0,
            0x943D3CAD, 0x14000172, 0x70747468, 0x2F2F3A73, 0x2E777777, 0x65636166,
            0x6B6F6F62, 0x6D6F632E, 0x6168732F, 0x672F6572, 0x4A4B312F, 0x6E434570,
            0x2F6A7766, 0x00000000,
        ),
        2: (
            0x10000109, 0xD2800628, 0xD280058A, 0xA9372BA8, 0xF81803A9, 0xD10243A0,
            0x943D3CAD, 0x14000172, 0x70747468, 0x2F2F3A73, 0x2E777777, 0x65636166,
            0x6B6F6F62, 0x6D6F632E, 0x6168732F, 0x672F6572, 0x4A4B312F, 0x6E434570,
            0x2F6A7766, 0x00000000,
        ),
    }),
    # Visit the R3 Website (0x5fd172f0) case 0xd6d440, after its check
    (0xD6D44C, "web", (
        0xD0FFB828, 0x9111E108, 0x3DC00100, 0xF840E108, 0x52800589, 0x52800800,
        0xA9377FBF, 0xF81803BF, 0x390063E9, 0x3C8193E0, 0xF80273E8, 0x3900BFFF,
        0x9442A9B1, 0xF0FFB0C8, 0x3DC1E100,
    ), {
        1: (
            0x10000109, 0xD2800428, 0xD280032A, 0xA9372BA8, 0xF81803A9, 0xD10243A0,
            0x943D3C6E, 0x14000133, 0x70747468, 0x2F2F3A73, 0x33727270, 0x7665642E,
            0x30366C65, 0x74656E2E, 0x0000002F,
        ),
        2: (
            0x10000109, 0xD2800428, 0xD280032A, 0xA9372BA8, 0xF81803A9, 0xD10243A0,
            0x943D3C6E, 0x14000133, 0x70747468, 0x2F2F3A73, 0x33727270, 0x7665642E,
            0x30366C65, 0x74656E2E, 0x0000002F,
        ),
    }),
    # v2: Invite Facebook Friends (0x4e3d) case 0xd6d510 -> OpenScreen(+0x158, "PartyPlayLocalScreen")
    (0xD6D510, "pp", (
        0x52800020, 0x97FDAED6, 0x360020E0, 0x941E9D1C, 0x370020A0,
    ), {
        2: (
            0xF940AE60, 0xF0FFB4A1, 0x91304021, 0x941CEA9D, 0x14000105,
        ),
    }),
    # Follow us on Twitter (0x4e43) case 0xd6d56c, after its check
    (0xD6D578, "tw", (
        0xB0FFB109, 0x91169D29, 0x3DC00120, 0x528D2989, 0x52800508, 0x72AD6DC9,
        0x52800600, 0xA9377FBF, 0xF81803BF, 0x3902C3E8, 0xB8049309, 0x3C839300,
        0x390317FF, 0x9442A965, 0xF0FFB0E8, 0x3DC1A900,
    ), {
        1: (
            0x10000109, 0xD2800428, 0xD280038A, 0xA9372BA8, 0xF81803A9, 0xD10243A0,
            0x943D3C23, 0x140000E8, 0x70747468, 0x2F2F3A73, 0x6F632E78, 0x52522F6D,
            0x33525033, 0x6966666F, 0x6C616963, 0x00000000,
        ),
        2: (
            0x10000109, 0xD2800428, 0xD280038A, 0xA9372BA8, 0xF81803A9, 0xD10243A0,
            0x943D3C23, 0x140000E8, 0x70747468, 0x2F2F3A73, 0x6F632E78, 0x52522F6D,
            0x33525033, 0x6966666F, 0x6C616963, 0x00000000,
        ),
    }),
    # Subscribe to our YouTube (0x4e45) case 0xd6d638, after its check
    (0xD6D644, "yt", (
        0xB0FFB449, 0x910EC129, 0x3DC00120, 0x528D2989, 0x52800508, 0x72AD6DC9,
        0x52800600, 0xA9377FBF, 0xF81803BF, 0x3901E3E8, 0xB8011309, 0x3C8793E0,
        0x390237FF, 0x9442A932, 0xD0FFB0E8, 0x3DC20100, 0xD0FFB328, 0x9126D908,
        0xF9003BE0, 0xAD400502,
    ), {
        1: (
            0x10000109, 0xD2800628, 0xD28005CA, 0xA9372BA8, 0xF81803A9, 0xD10243A0,
            0x943D3BF0, 0x140000B5, 0x70747468, 0x2F2F3A73, 0x2E777777, 0x74756F79,
            0x2E656275, 0x2F6D6F63, 0x6F725040, 0x7463656A, 0x73736552, 0x63657275,
            0x6E6F6974, 0x0000332D,
        ),
        2: (
            0x10000109, 0xD2800628, 0xD28005CA, 0xA9372BA8, 0xF81803A9, 0xD10243A0,
            0x943D3BF0, 0x140000B5, 0x70747468, 0x2F2F3A73, 0x2E777777, 0x74756F79,
            0x2E656275, 0x2F6D6F63, 0x6F725040, 0x7463656A, 0x73736552, 0x63657275,
            0x6E6F6974, 0x0000332D,
        ),
    }),
    # Get Support (0x5254d3ea) case 0xd6d704, after its check
    (0xD6D710, "sup", (
        0xB0009008, 0xF9431908, 0x39400108, 0x34001228, 0x90009008, 0xF9456508,
        0xF9400100, 0xF9400008,
    ), {
        1: (
            0x10001289, 0xD2800628, 0xD28004AA, 0xA9372BA8, 0xF81803A9, 0xD10243A0,
            0x943D3BBD, 0x14000082,
        ),
        2: (
            0x10001289, 0xD2800628, 0xD28004AA, 0xA9372BA8, 0xF81803A9, 0xD10243A0,
            0x943D3BBD, 0x14000082,
        ),
    }),
    # Follow us on Instagram (0x5fd172e8) case 0xd6d73c, after its check
    (0xD6D748, "dc", (
        0xB0FFB408, 0x91017508, 0x3DC00100, 0xF840E108, 0x52800589, 0x52800600,
        0xA9377FBF, 0xF81803BF, 0x390123E9, 0x3C8493E0, 0xF80573E8, 0x39017FFF,
        0x9442A8F2, 0x90FFB0E8, 0x3DC1E100, 0xF90023E0, 0x90009009, 0xD0FFB2E8,
        0x3D800FE0, 0xF943D529, 0x9115E108, 0xAD400101, 0xF841E108, 0xF9400133,
        0x3900981F, 0xAD000001, 0xF801E008,
    ), {
        1: (
            0x10000109, 0xD2800A28, 0xD280096A, 0xA9372BA8, 0xF81803A9, 0xD10243A0,
            0x943D3BAF, 0x14000074, 0x70747468, 0x2F2F3A73, 0x63736964, 0x2E64726F,
            0x702F6767, 0x656A6F72, 0x722D7463, 0x72757365, 0x74636572, 0x2D6E6F69,
            0x6966666F, 0x6C616963, 0x7265732D, 0x2D726576, 0x32383431, 0x36383838,
            0x35383938, 0x31373934, 0x00373939,
        ),
        2: (
            0x10000109, 0xD2800A28, 0xD280096A, 0xA9372BA8, 0xF81803A9, 0xD10243A0,
            0x943D3BAF, 0x14000074, 0x70747468, 0x2F2F3A73, 0x63736964, 0x2E64726F,
            0x702F6767, 0x656A6F72, 0x722D7463, 0x72757365, 0x74636572, 0x2D6E6F69,
            0x6966666F, 0x6C616963, 0x7265732D, 0x2D726576, 0x32383431, 0x36383838,
            0x35383938, 0x31373934, 0x00373939,
        ),
    }),
    # Reddit URL, in Get Support's old EA Help code
    (0xD6D960, "supdata", (
        0xD10183A8, 0x97FDA86D, 0x90FFB720, 0x91364400, 0x940CF3D6, 0xAA0003F4,
        0x9442A89E, 0xB100401F, 0x54001BE2, 0xAA0003F3,
    ), {
        1: (
            0x70747468, 0x2F2F3A73, 0x2E777777, 0x64646572, 0x632E7469, 0x722F6D6F,
            0x6165522F, 0x6361526C, 0x33676E69, 0x0000002F,
        ),
        2: (
            0x70747468, 0x2F2F3A73, 0x2E777777, 0x64646572, 0x632E7469, 0x722F6D6F,
            0x6165522F, 0x6361526C, 0x33676E69, 0x0000002F,
        ),
    }),
    # com_hook, relabel, hide, label texts, in that old EA Help code
    (0xD6DB3C, "hook", (
        0xF9400008, 0xF9401108, 0xD63F0100, 0x90009008, 0xF942E908, 0xF9400100,
        0xF9400008, 0xF9401508, 0xD63F0100, 0xD0FFB689, 0x91378129, 0x3DC00120,
        0xAA0003F3, 0x52800488, 0x528CAC69, 0x52800400, 0x381883A8, 0x780C1309,
        0x3C8B1300, 0x3819B3BF, 0x9442A7ED, 0xB0FFB7E9, 0xF0FFB0C8, 0x91113D29,
        0x3DC10900, 0x3CC09121, 0x3DC00122, 0xF81803A0, 0x3C9703A0, 0x3C809001,
        0x3D800002, 0x3900641F, 0xF9400268, 0xD101E3A1, 0xD10243A2, 0xAA1303E0,
        0xF9405909, 0xD10183A8, 0xD63F0120, 0xF0FFB6C9, 0x9121D129, 0xF9400129,
        0xD0FFB322, 0x52800288, 0x528CADAA, 0x91257442, 0xD10183A0, 0x910323E1,
        0x390323E8, 0x7805930A, 0xF8051309, 0x39034FFF, 0x943D1C1E, 0x943D1EC4,
        0x394323E8, 0x36000068, 0xF9406FE0, 0x9442A7CC, 0xF85D83B3, 0xB4000353,
        0xF85E03B4, 0xEB13029F, 0x540000C1, 0xAA1303E0, 0x14000013, 0xEB15027F,
        0xAA1503F4, 0x540001E0, 0x385E8288, 0x370000A8, 0x385D0288, 0xD100C295,
        0x3607FF28, 0x14000006, 0xF85F8280, 0x9442A7BA, 0x385D0288, 0xD100C295,
        0x3607FE68, 0xF85E0280, 0x9442A7B5, 0x17FFFFF0, 0xF85D83A0, 0xF81E03B3,
        0x9442A7B1, 0x385B83A8, 0x37000108, 0x385A03A8, 0x37000148, 0x385703A8,
        0x37000188, 0x385883A8, 0x3607E448, 0x1400000D, 0xF85C83A0, 0x9442A7A6,
        0x385A03A8, 0x3607FF08, 0xF85B03A0, 0x9442A7A2,
    ), {
        1: (
            0xA9BF7BFD, 0x910003FD, 0x940BF3C2, 0xAA1303E0, 0x5289C641, 0x10000882,
            0x94000017, 0xAA1303E0, 0x5289C681, 0x100008E2, 0x94000013, 0xAA1303E0,
            0x528E4921, 0x72ABFA21, 0x10000902, 0x9400000E, 0xAA1303E0, 0x528E4981,
            0x72ABFA21, 0x300008E2, 0x94000009, 0xAA1303E0, 0x5289C801, 0x94000027,
            0xAA1303E0, 0x5289C7A1, 0x94000024, 0xA8C17BFD, 0xD65F03C0, 0xA9BC7BFD,
            0x910003FD, 0xF9000BE2, 0xF9400008, 0xF9401508, 0x2A1F03E2, 0x2A1F03E3,
            0xD63F0100, 0xB40002E0, 0x90009002, 0xF9464C41, 0xF946A442, 0xAA1F03E3,
            0x9442A827, 0xB4000220, 0xF9000FE0, 0xA9027FFF, 0xF9001BFF, 0x910083E0,
            0xF9400BE1, 0x9421B11B, 0xF9400FE0, 0x79448002, 0x39490808, 0x33101D02,
            0x910083E1, 0x940DA0C8, 0x394083E8, 0x36000068, 0xF9401BE0, 0x9442A7CA,
            0xA8C47BFD, 0xD65F03C0, 0xA9BF7BFD, 0x910003FD, 0xF9400008, 0xF9401508,
            0x2A1F03E2, 0x2A1F03E3, 0xD63F0100, 0xA8C17BFD, 0xB4000040, 0x140D3E66,
            0xD65F03C0, 0x6E696F4A, 0x65687420, 0x63614620, 0x6F6F6265, 0x6F63206B,
            0x6E756D6D, 0x00797469, 0x6C616552, 0x63615220, 0x20676E69, 0x6E6F2033,
            0x64655220, 0x00746964, 0x6E696F4A, 0x72756F20, 0x73694420, 0x64726F63,
            0x73695600, 0x74207469, 0x50206568, 0x77205252, 0x69736265, 0x00006574,
        ),
        2: (
            0xA9BF7BFD, 0x910003FD, 0x940BF3C2, 0xAA1303E0, 0x5289C641, 0x100008A2,
            0x94000018, 0xAA1303E0, 0x5289C681, 0x10000902, 0x94000014, 0xAA1303E0,
            0x528E4921, 0x72ABFA21, 0x10000922, 0x9400000F, 0xAA1303E0, 0x528E4981,
            0x72ABFA21, 0x30000902, 0x9400000A, 0xAA1303E0, 0x5289C801, 0x94000028,
            0xAA1303E0, 0x5289C7C1, 0x700008C2, 0x94000003, 0xA8C17BFD, 0xD65F03C0,
            0xA9BC7BFD, 0x910003FD, 0xF9000BE2, 0xF9400008, 0xF9401508, 0x2A1F03E2,
            0x2A1F03E3, 0xD63F0100, 0xB40002E0, 0x90009002, 0xF9464C41, 0xF946A442,
            0xAA1F03E3, 0x9442A826, 0xB4000220, 0xF9000FE0, 0xA9027FFF, 0xF9001BFF,
            0x910083E0, 0xF9400BE1, 0x9421B11A, 0xF9400FE0, 0x79448002, 0x39490808,
            0x33101D02, 0x910083E1, 0x940DA0C7, 0x394083E8, 0x36000068, 0xF9401BE0,
            0x9442A7C9, 0xA8C47BFD, 0xD65F03C0, 0xA9BF7BFD, 0x910003FD, 0xF9400008,
            0xF9401508, 0x2A1F03E2, 0x2A1F03E3, 0xD63F0100, 0xA8C17BFD, 0xB4000040,
            0x140D3E65, 0xD65F03C0, 0x6E696F4A, 0x65687420, 0x63614620, 0x6F6F6265,
            0x6F63206B, 0x6E756D6D, 0x00797469, 0x6C616552, 0x63615220, 0x20676E69,
            0x6E6F2033, 0x64655220, 0x00746964, 0x6E696F4A, 0x72756F20, 0x73694420,
            0x64726F63, 0x73695600, 0x74207469, 0x50206568, 0x77205252, 0x69736265,
            0x50006574, 0x79747261, 0x616C5020, 0x00000079,
        ),
    }),
    # Community setup 0xd6ddac: bl 0x106aa4c (hide the ticket dot) -> bl com_hook
    (0xD6DE34, "hook-call", (
        0x940BF306,
    ), {
        1: (
            0x97FFFF42,
        ),
        2: (
            0x97FFFF42,
        ),
    }),
]


def load(path):
    data = open(path, "rb").read()
    return bytearray(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def words(d, addr, n):
    return struct.unpack_from(f"<{n}I", d, addr)


def prr_login_v2(d):
    """True when rr3_prr_login.py v2 holds Get Support and the setup call."""
    return all(words(d, a, len(ws)) == ws for a, ws in PRR_LOGIN_V2.items())


def image(v, dev, by):
    """The words a part holds with version v (0 = develified)."""
    ws = by.get(v, ()) if v else ()
    return tuple(ws) + tuple(dev[len(ws):])


def version(d):
    """0 not patched (develified, or Get Support held by prr-login v2),
    1 or 2 patched, None unrecognised."""
    for v in (0, *VERSIONS):
        ok = True
        for addr, _, dev, by in PARTS:
            got = words(d, addr, len(dev))
            want = image(v, dev, by)
            if got == want:
                continue
            if not v and addr in PRR_LOGIN_V2:
                n = len(PRR_LOGIN_V2[addr])
                if got[:n] == PRR_LOGIN_V2[addr] and got[n:] == dev[n:]:
                    continue
            ok = False
            break
        if ok:
            return v
    return None


def state(d):
    v = version(d)
    if v is None:
        return None
    if not v:
        return "develified" + (" (Get Support is rr3_prr_login.py v2's PRR website)" if prr_login_v2(d) else "")
    links = "Facebook group, Reddit, X, YouTube, Discord, PRR website"
    if v == 1:
        return f"patched v1 ({links}; Invite Facebook Friends and the EA Help logo hidden)"
    return f"patched v2 ({links}; Invite Facebook Friends = Party Play; EA Help logo hidden)"


def contents(d):
    """`patches` entry for rr3_build.py: '' not patched, None unrecognised."""
    v = version(d)
    return None if v is None else "" if v == 0 else "community" if v == 1 else f"community@v{v}"


def write(d, v):
    for addr, _, dev, by in PARTS:
        ws = image(v, dev, by)
        struct.pack_into(f"<{len(ws)}I", d, addr, *ws)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").add_argument("lib")
    p = sub.add_parser("patch")
    p.add_argument("inp")
    p.add_argument("out")
    p.add_argument("--restore", action="store_true", help="put the develified bytes back")
    p.add_argument("--version", type=int, choices=VERSIONS, default=VERSION,
                   help=f"write this version (default {VERSION}; 1 = b54-stable's, Invite hidden)")
    a = ap.parse_args()

    d = load(a.lib if a.cmd == "check" else a.inp)
    s = state(d)
    if s is None:
        sys.exit("unexpected bytes in the Community handler or its setup: not the v14.0.1 develified build?")
    if a.cmd == "check":
        print(s)
        return
    if prr_login_v2(d):
        sys.exit("rr3_prr_login.py v2 holds Community > Get Support: first run "
                 "rr3_prr_login.py patch IN OUT --version 3 (leaves Community to this tool)")
    write(d, 0 if a.restore else a.version)
    open(a.out, "wb").write(gzip.compress(bytes(d)) if a.out.endswith(".gz") else bytes(d))
    print(f"{a.out}: {state(d)}")


if __name__ == "__main__":
    main()
