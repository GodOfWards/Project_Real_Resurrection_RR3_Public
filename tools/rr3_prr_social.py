#!/usr/bin/env python3
"""Our account in the game's Facebook slot (issue #220 part 3, #163
option B), by patching libRealRacing3.so (v14.0.1, arm64, develified
build). Version 3, untested in game (v1 and v2 untested too).
Guide: docs/prr-social.md.

The game asks "logged in to a social network?" in 71 places (Race Teams,
leaderboard friends tab, LTS/TTC, OMP, ...). With this patch the answer is
yes: the Facebook slot holds a Project Real Resurrection user, and the
friends list comes from our server (rr3_cc_server.py v5.16+, 10556) instead
of Facebook.

  0x1cfb838  Cloudcell reply reader 0x1cfb784, the member id store
             `str w21, [x22]` -> `bl 0x1583d04` (set_user). It runs the
             store, then, unless the id is 1 (no member), sets the Facebook
             user with 0x1c7e634(manager, "prr:<member>", <name>, "", "")
             (v3; the setter's slots are id +0x90, name +0xa8, token +0xc0,
             a fourth +0xd8, #403),
             name = the leaderboard username (files/doc/leaderboard_username.dat,
             rr3_username.py) or empty. Runs on the first reply of each game
             start and when the id changes. The setter sends social event 12,
             which makes the RacerManager reload friends at once.
  0x1c7a524  FacebookManager IsLoggedIn (ISocialManager vfunc 0x30,
             0x1c7a4f8): `ldur x0, [x0, #-0x80]` -> `b 0x1c7a540`. The user is
             no longer checked with Java GetSessionValid (always false on our
             APK) and so never logged out: "logged in" = a non-empty
             authenticator.
  0x1c66098  AndroidFacebookWorker LoadFriendVector (vfunc 0x58),
  0x1c65c68  PermissionCheck (vfunc 0x40) and
  0x1c66550  LoadAvatarUrl: the first five instructions become the game's
             own failure path (as at 0x1c66134): `ldr x8, [x0, #8] ;
             mov w9, #1 ; strb w9, [x8, #0x12] ; str xzr, [x0, #8] ; ret`.
             The request completes with no data and no Java call. For
             LoadFriendVector the completion passes a null list to
             SocialMedia::OnFriends (0x1d06b78), which then sends 10556 to
             our server, and to the RacerManager handler (0x134f9e4).
  0x1583d04  new code (396 bytes, tools/asm/rr3_prr_social.s) in this tool's
             slice 0x1583d04..0x1584104 of the dead physics-state compare
             (tables/lib-code-caves.csv); the rest of the slice is zeroed so
             tools/rr3_patch_sites.py shows the whole slice as ours.


v2 (issue #278) adds:
  0x1350df0  RacerManager friends sync 0x1350ca4 (from the event map):
             `b.ne 0x1350e18` -> `b 0x1350e18`. The game sent subsync 10472
             (friends' details: names, member ids, stats, owned cars, the
             only source of the friends screens and "N friends own this
             car") only when it had social friend ids or a Race Team. Our
             friends list is empty, so 10472 was never sent. Now it goes
             out like it would with ids: on the first visit, then when 600 s
             have passed or a refresh is forced. rr3_cc_server.py answers
             it from data/rr3-friends.json (the server part of #278).

v3 (issue #403): the setter's strings in the right slots. Its log
"CC Changing Authenticator (%s) - ID: %s Name: %s Token: %s" prints the
network name first (vfunc +0x108), so its arguments are (id, name, token,
fourth), stored at +0x90/+0xa8/+0xc0/+0xd8. v1/v2 passed ("prr",
"prr:<member>", <name>, ""): id "prr", name "prr:<member>", token = the
username. v3 passes ("prr:<member>", <name>, "", ""): three words of the
code (x1..x3 before the call). IsLoggedIn tests the id, still non-empty;
10556's own id (when a friend entry has the network) is now
"prr:<member>".

FeedPost, PhotoPost, FriendInvite and DecodeAvatar are left alone.

Usage:
  rr3_prr_social.py check LIB
  rr3_prr_social.py patch IN OUT [--restore] [--version 1|2|3]
IN may be gzipped; OUT is written uncompressed (or gzipped if it ends in .gz).
"""
import argparse
import gzip
import struct
import sys

VERSION = 3
CAVE, SLICE_END = 0x1583D04, 0x1584104
SET_USER = CAVE
# tools/asm/rr3_prr_social.s linked for 0x1583d04 (build line in that file).
CODE = (
    0xB90002D5, 0x710006BF, 0x54000041, 0xD65F03C0, 0xD106C3FF, 0xA9007BFD,
    0x910003FD, 0xA9037FFF, 0xA9047FFF, 0xA9057FFF, 0xA9067FFF, 0xA9077FFF,
    0xA9087FFF, 0x100009A9, 0x79400128, 0x780313E8, 0x39400928, 0x3900CFE8,
    0x528000C8, 0x3900C3E8, 0x910127E0, 0xD28002C1, 0xAA0903E2, 0x2A1503E3,
    0x942256B3, 0x531F7808, 0x390123E8, 0x9102C3E0, 0x97F4869F, 0xAA0003E3,
    0x9102C3E0, 0xD2802001, 0x70000762, 0x942256AA, 0x9102C3E0, 0xF0FF7541,
    0x911FF821, 0x94224FD2, 0xB4000460, 0xF90013E0, 0xAA0003E3, 0x910243E0,
    0xD2800021, 0xD2800382, 0x9422503B, 0xF90017E0, 0xF94013E0, 0x94224FCC,
    0xF94017E0, 0xF100701F, 0x540002E1, 0xB94093E8, 0x528A4A49, 0x72A9CAA9,
    0x6B09011F, 0x54000241, 0xB94097E8, 0x7100051F, 0x540001EB, 0xB9409BE8,
    0x51000D09, 0x7100353F, 0x54000168, 0x531F7909, 0x390183E9, 0xD280000A,
    0x910273EB, 0x386A6969, 0x910187EB, 0x382A6969, 0x9100054A, 0xEB08015F,
    0x54FFFF43, 0xD0004F48, 0xF942E908, 0xF9400108, 0xF9401500, 0xF9400008,
    0xF9400908, 0xD63F0100, 0xB40000E0, 0xD1022000, 0x9100C3E1, 0x910123E2,
    0x910183E3, 0x9101E3E4, 0x941BE9F6, 0xA9407BFD, 0x9106C3FF, 0xD65F03C0,
    0x3A727270, 0x25007525, 0x61656C73, 0x62726564, 0x6472616F, 0x6573755F,
    0x6D616E72, 0x61642E65, 0x00000074,
)
# v3 (#403): x1..x3 before the setter call = id, name, token (v1/v2: auth, id, name).
CODE3 = CODE[:82] + (0x910123E1, 0x910183E2, 0x9101E3E3) + CODE[85:]
assert CODE[82:85] == (0x9100C3E1, 0x910123E2, 0x910183E3) and len(CODE3) == len(CODE)
# The words of the dead function in this tool's slice (256 words).
CAVE_DEVELIFIED = (
    0xBD4EFE61, 0x1E212000, 0x54004941, 0xBD4F0280, 0xBD4F0261, 0x1E212000,
    0x540049C1, 0xBD4F0680, 0xBD4F0661, 0x1E212000, 0x54004A41, 0xBD4EDE80,
    0xBD4EDE61, 0x1E212000, 0x54004AC1, 0x2A1503E0, 0xA9424FF4, 0xF9400BF5,
    0xA8C37BFD, 0xD65F03C0, 0xF0FF7240, 0x912F2400, 0x97EC6F2F, 0x2A1F03F5,
    0xB9414688, 0xB9414669, 0x6B09011F, 0x54FFDA00, 0x90FF77E0, 0x91243C00,
    0x97EC6F27, 0x2A1F03F5, 0xB9414A88, 0xB9414A69, 0x6B09011F, 0x54FFD980,
    0xF0FF74E0, 0x91321800, 0x97EC6F1F, 0x2A1F03F5, 0xB9414E88, 0xB9414E69,
    0x6B09011F, 0x54FFD900, 0xD0FF73E0, 0x912DFC00, 0x97EC6F17, 0x2A1F03F5,
    0xB9415288, 0xB9415269, 0x6B09011F, 0x54FFD880, 0xD0FF7320, 0x91048C00,
    0x97EC6F0F, 0x2A1F03F5, 0xB9415688, 0xB9415669, 0x6B09011F, 0x54FFD800,
    0xD0FF7320, 0x9104E400, 0x97EC6F07, 0x2A1F03F5, 0xB9415A88, 0xB9415A69,
    0x6B09011F, 0x54FFD780, 0xD0FF71C0, 0x911C8000, 0x97EC6EFF, 0x2A1F03F5,
    0xB9415E88, 0xB9415E69, 0x6B09011F, 0x54FFD700, 0xF0FF7780, 0x913D3800,
    0x97EC6EF7, 0x2A1F03F5, 0xB9416288, 0xB9416269, 0x6B09011F, 0x54FFD680,
    0x90FF7540, 0x910BD000, 0x97EC6EEF, 0x2A1F03F5, 0xB9417688, 0xB9417669,
    0x6B09011F, 0x54FFD600, 0xF0FF74A0, 0x910E1C00, 0x97EC6EE7, 0x2A1F03F5,
    0xB9417A88, 0xB9417A69, 0x6B09011F, 0x54FFD580, 0xD0FF7640, 0x91033000,
    0x97EC6EDF, 0x2A1F03F5, 0xB9417E88, 0xB9417E69, 0x6B09011F, 0x54FFD500,
    0xF0FF7740, 0x91244C00, 0x97EC6ED7, 0x2A1F03F5, 0xB9418288, 0xB9418269,
    0x6B09011F, 0x54FFD480, 0xF0FF7700, 0x910CD000, 0x97EC6ECF, 0x2A1F03F5,
    0x91064280, 0x91064261, 0x97FA8583, 0x3707D400, 0xF0FF70A0, 0x912B9800,
    0x97EC6EC7, 0x2A1F03F5, 0xB941AA88, 0xB941AA69, 0x6B09011F, 0x54FFD380,
    0xD0FF7680, 0x91340C00, 0x97EC6EBF, 0x2A1F03F5, 0xB941AE88, 0xB941AE69,
    0x6B09011F, 0x54FFD300, 0xD0FF7640, 0x91038400, 0x97EC6EB7, 0x2A1F03F5,
    0xB941B288, 0xB941B269, 0x6B09011F, 0x54FFD280, 0xB0FF75C0, 0x91098000,
    0x97EC6EAF, 0x2A1F03F5, 0xB941B688, 0xB941B669, 0x6B09011F, 0x54FFD200,
    0x90FF7100, 0x91119000, 0x97EC6EA7, 0x2A1F03F5, 0xB941BA88, 0xB941BA69,
    0x6B09011F, 0x54FFD180, 0xF0FF74A0, 0x910E9800, 0x97EC6E9F, 0x2A1F03F5,
    0xB941BE88, 0xB941BE69, 0x6B09011F, 0x54FFD100, 0xD0FF7360, 0x911DD000,
    0x97EC6E97, 0x2A1F03F5, 0xB941C288, 0xB941C269, 0x6B09011F, 0x54FFD080,
    0xF0FF7460, 0x91099000, 0x97EC6E8F, 0x2A1F03F5, 0xB941C688, 0xB941C669,
    0x6B09011F, 0x54FFD000, 0xF0FF70A0, 0x912BEC00, 0x97EC6E87, 0x2A1F03F5,
    0xB941CA88, 0xB941CA69, 0x6B09011F, 0x54FFCF80, 0xD0FF74A0, 0x910EF400,
    0x97EC6E7F, 0x2A1F03F5, 0xB941CE88, 0xB941CE69, 0x6B09011F, 0x54FFCF00,
    0xF0FF7560, 0x912FD000, 0x97EC6E77, 0x2A1F03F5, 0xB941DE88, 0xB941DE69,
    0x6B09011F, 0x54FFCE80, 0x90FF75C0, 0x9109CC00, 0x97EC6E6F, 0x2A1F03F5,
    0xB941E288, 0xB941E269, 0x6B09011F, 0x54FFCE00, 0x90FF75C0, 0x9109CC00,
    0x97EC6E67, 0x2A1F03F5, 0xB941E688, 0xB941E669, 0x6B09011F, 0x54FFCD80,
    0x90FF75C0, 0x9109CC00, 0x97EC6E5F, 0x2A1F03F5, 0xB941EA88, 0xB941EA69,
    0x6B09011F, 0x54FFCD00, 0x90FF75C0, 0x9109CC00, 0x97EC6E57, 0x2A1F03F5,
    0xB941EE88, 0xB941EE69, 0x6B09011F, 0x54FFCC80, 0x90FF75C0, 0x9109CC00,
    0x97EC6E4F, 0x2A1F03F5, 0xB941F288, 0xB941F269, 0x6B09011F, 0x54FFCC00,
    0x90FF75C0, 0x9109CC00, 0x97EC6E47, 0x2A1F03F5,
)
SLICE_WORDS = (SLICE_END - CAVE) // 4
# The game's failure path for a worker request (0x1c66134).
FAIL = (0xF9400408, 0x52800029, 0x39004909, 0xF900041F, 0xD65F03C0)
# (address, develified words, {version: words}); version v writes the newest
# revision <= v, the develified words when there is none. .text VMA == file
# offset in this build.
PARTS = [
    # code + zeros to the end of the slice
    (CAVE, CAVE_DEVELIFIED, {1: CODE + (0,) * (SLICE_WORDS - len(CODE)),
                             3: CODE3 + (0,) * (SLICE_WORDS - len(CODE3))}),
    # reply reader: str w21, [x22] -> bl set_user
    (0x1CFB838, (0xB90002D5,), {1: (0x97E22133,)}),
    # IsLoggedIn: ldur x0, [x0, #-0x80] -> b 0x1c7a540 (no GetSessionValid, no logout)
    (0x1C7A524, (0xF8580000,), {1: (0x14000007,)}),
    # LoadFriendVector, PermissionCheck, LoadAvatarUrl -> fail at once
    (0x1C66098, (0xF81D0FF5, 0xA9014FF4, 0xA9027BFD, 0x910083FD, 0xF9400008), {1: FAIL}),
    (0x1C65C68, (0xA9BB67FA, 0xA9015FF8, 0xA90257F6, 0xA9034FF4, 0xA9047BFD), {1: FAIL}),
    (0x1C66550, (0xF81C0FF7, 0xA90157F6, 0xA9024FF4, 0xA9037BFD, 0x9100C3FD), {1: FAIL}),
    # v2: friends sync gate: b.ne 0x1350e18 -> b 0x1350e18 (10472 with no social ids)
    (0x1350DF0, (0x54000141,), {2: (0x1400000A,)}),
]
VERSIONS = (1, 2, 3)
# The cave (tables/lib-code-caves.csv) requires nothing. The name file comes
# from rr3_username.py at run time; without it the name is empty.
REQUIRES = []


def load(path):
    data = open(path, "rb").read()
    return bytearray(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def words(part, v):
    """A part's words in version v: the newest revision <= v, else develified."""
    addr, develified, by_version = part
    if v == 0:
        return develified
    have = [k for k in by_version if k <= v]
    return by_version[max(have)] if have else develified


def version(d):
    """0 develified, 1..3 patched, None unrecognised."""
    have = [struct.unpack_from(f"<{len(p[1])}I", d, p[0]) for p in PARTS]
    for v in (0,) + VERSIONS:
        if all(h == words(p, v) for h, p in zip(have, PARTS)):
            return v
    return None


def state(d):
    v = version(d)
    if v is None:
        return None
    if not v:
        return "develified"
    return f"patched v{v} (our account in the Facebook slot" + (", friends' details sync 10472)" if v >= 2 else ")")


def contents(d):
    """`patches` entry for rr3_build.py: '' develified, None unrecognised.
    v1: prr-social; v2: prr-social@v2; v3: prr-social@v3."""
    v = version(d)
    return None if v is None else "" if v == 0 else "prr-social" if v == 1 else f"prr-social@v{v}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").add_argument("lib")
    p = sub.add_parser("patch")
    p.add_argument("inp")
    p.add_argument("out")
    p.add_argument("--restore", action="store_true", help="put the develified bytes back")
    p.add_argument("--version", type=int, choices=VERSIONS, default=VERSION,
                   help="patch version to write (default %(default)s; 2 = the v1/v2 string order, "
                        "1 = also without the 10472 gate)")
    a = ap.parse_args()

    d = load(a.lib if a.cmd == "check" else a.inp)
    s = state(d)
    if s is None:
        sys.exit("unexpected bytes at a patch site or in the code area: not the v14.0.1 develified build?")
    if a.cmd == "check":
        print(s)
        return
    for p in PARTS:
        w = words(p, 0 if a.restore else a.version)
        struct.pack_into(f"<{len(w)}I", d, p[0], *w)
    open(a.out, "wb").write(gzip.compress(bytes(d)) if a.out.endswith(".gz") else bytes(d))
    print(f"{a.out}: {state(d)}")


if __name__ == "__main__":
    main()
