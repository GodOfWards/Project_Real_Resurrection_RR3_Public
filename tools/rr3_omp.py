#!/usr/bin/env python3
"""Online Multiplayer (OMP) patches for libRealRacing3.so (v14.0.1, arm64,
develified build), issue #86. Parts (--parts, comma-separated; default
nosocial,host):

  nosocial  OMP no longer asks for a social network log-in.
  host      OMP matchmaking connects to our master server (--mp-host).
  stock     OMP races are stock: no upgrades, default tuning (issue #227;
            only when asked for with --parts).
  nolevel   OMP is open at any player level (only when asked for with
            --parts).

nosocial: three OMP paths call the "logged in to any social account?"
check 0xcd8578 (Facebook, Google Play Games or Apple Sign In, none of which
works on a re-signed develified.apk) and, when it returns false, show
GAMETEXT_OMP_SOCIAL_MEDIA_NOT_AUTHENTICATED ("Please log in to a social
network account to enter Online Multiplayer", Later / Login):

  0xf37448   tbnz w0, #0, 0xf37454  (37000060) -> b 0xf37454  (14000003)
             OMP entry task 0xf373a8 (popup 0xf37570)
  0x149ae2c  tbz  w0, #0, 0x149afb0 (36000c20) -> nop         (d503201f)
             OMP event screen 0x149ade0, state 3 (popup 0x149afb0)
  0x14ca1bc  tbz  w0, #0, 0x14ca29c (36000700) -> nop         (d503201f)
             OMP launch from car select 0x14ca1b8 (popup 0x14ca29c)

Each patched branch goes on as if a social account were logged in. Only
these OMP paths change; the check itself (36 callers: friends
leaderboards, LTS / TTC, Race Teams, cloud save, ...) is untouched.
Versions: v1 (b32) patched only 0xf37448, and Race Now still showed the
pop-up (2026-10-21). v2 (default, confirmed with b33) patches all three.
`--nosocial-version 1` writes v1 for testing.

host: the master server address (getter 0xbb4450, and 0xbb3d20, 0xbb4424,
0xbb44e8, which read the same table) comes from two 6-entry tables (normal
and China) whose 12 pointers are R_AARCH64_RELATIVE relocations in
.rela.dyn, pointing to 5 strings (0037-mp6 / 0037-mp3 / be01prr3mp01
.cloudcell.com, 159.153.46.7, 159.153.46.8). This part sets all 12
addends (.rela.dyn file offsets 0xa10d8 + 24*n + 16) to 0x3c13e6 and
writes HOST there over "be01prr3mp01.cloudcell.com" (27 bytes with its
0, so HOST is at most 26 characters, the rest filled with 0). The game
then always connects to HOST. An IPv4 literal or a host name both work.
Research: analysis/online-multiplayer.md, "Q6"; social log-in: "Q8".

--mp-host2 HOST2 (at most 22 characters) adds a second master server: the
odd table entries (1, 3, 5 of each table) point to HOST2, written over
"0037-mp6.cloudcell.com" at 0x47ae0c (23 bytes with its 0), the even ones
to HOST. The getter uses entry ([Character+0x10cf8] % 6); the counter
starts at 0 (HOST) and the debug menu button `OMP|MP Server:` (0xa68544 ->
0xbb4620) adds 1, so each tap switches between HOST and HOST2.

--mp-port PORT (default 60000, the develified port) sets the master server UDP
port, fixed in code as `mov wN, #0xea60` at 0xbb0f88 (w3, connect by IPv4),
0xbb1020 (w2, connect by name) and 0xbb4504 (w4, start-up getaddrinfo):
each becomes `mov wN, #PORT` (52800000 | PORT << 5 | N). The game server
port is not in the lib: our master server sends it in its game server
list (rr3_mp_server.py --game-port).

stock (v1, issue #227): 0x1311b30 fills a car performance record from
the car's state ([car+0x190]): the upgrade set with `bl 0x1551688` at
0x1311b84, then the tuning pointer (x21 = [[x20]+0x10], 0x1311b88 and
0x1311b8c), and 0x1311b90 `cbz x21` takes the "no tuning" path (default
tuning from the car description). It is the only code that reads a car's
upgrades and tuning into a record, so whichever caller builds the race
car's record goes through it. This part writes:

  0x1311b84  bl 0x1551688 (9408fec1)  -> bl 0x1584304 (9409c9e0)
  0x1311b88  ldr x8, [x20] (f9400288) -> nop
  0x1311b8c  ldr x21, [x8, #0x10] (f9400915) -> nop
  0x1584304  19 words (tools/asm/rr3_omp_stock.s) in the dead physics-
             state compare cave (slice 0x1584304..0x1584350)

The cave makes the original copy, then, while an OMP match is in progress
(OMP state [[GOT 0x1f6dac0]]+0x4cc in 3..8: StartMatch sent to results;
exit paths set it back to 0), sets the record's upgrade levels to 0
(0x155354c, the debug menu's Remove Upgrades, on the record's own arrays:
the copy is deep) and x21 = 0; otherwise it runs the two moved
instructions. The car, the garage and the save are never written. OMP car
select (state 0) still shows the upgraded PR. Confirmed in game (Tom,
2026-11-04).

stock v2 (issue #325, the default): the same three sites, the bl goes to
0x15844d4 (38 words, tools/asm/rr3_omp_stock_v2.s, slice
0x15844d4..0x158456c of the same cave; v1's slice stays develified). Stock
also when a game mode is running (game = [[GOT 0x1f6d5d8]],
[game+0x10d88] != 0; cleared at race end, 0x10af2e4) and the current
event's stream ([[[game+0x113a0]+0x130]+0x108]+0x10) is a competition LTS
(0xc4080c: sub type 2), i.e. Weekly Time Trials and other TTC. Normal Time
Trials, menus and the garage keep the real upgrades. --stock-version 1
writes v1. Untested in game.
Research and design: analysis/online-multiplayer.md, "Stock cars in OMP
without touching the garage".

nolevel (v1): the OMP card (OnlineMultiplayerCard, 0xa99bd4) compares the
player level (0xd20d54) with the OMP unlock level ([[GOT 0x1f6d960]]+0x574,
from the game's economy data, read by 0xd0bf10; "Reach Player Level 6",
GAMETEXT_OMP_LOCKED_ERROR) and below it shows the locked landing page
(0xa9a924, OnlineMultiPlayerLandingPage.xml, "Reach Player Level [nLevel]
to unlock Online Multiplayer") instead of OMP. Its override,
omp_unlock_level_override (with override_client_unlock_levels, 0x10b11f0),
is a Firebase Remote Config key, which no server of ours answers. This
part writes

  0xa99cac  b.ge 0xa99ce0 (540001aa) -> b 0xa99ce0 (1400000d)

so the card always goes on as if the level were reached. Only the card
changes; the "You have unlocked Online Multiplayer!" pop-up (0x9e2ba0)
still follows the real level. Untested in game.

Usage:
  rr3_omp.py check LIB
  rr3_omp.py patch IN OUT [--parts nosocial,host,stock,nolevel] [--nosocial-version {1,2}]
                          [--mp-host 127.0.0.1] [--mp-host2 HOST2]
                          [--mp-port 60000] [--restore]
IN may be gzipped; OUT is written uncompressed (or gzipped if it ends in .gz).
"""
import argparse
import gzip
import re
import struct
import sys

NOP = 0xD503201F
# nosocial: {version: [(site, develified word, patched word), ...]}.
# .text VMA == file offset.
NOSOCIAL = {
    1: [(0xF37448, 0x37000060, 0x14000003)],                # tbnz w0, #0, 0xf37454 -> b 0xf37454
    2: [(0xF37448, 0x37000060, 0x14000003),
        (0x149AE2C, 0x36000C20, NOP),                       # tbz w0, #0, 0x149afb0 -> nop
        (0x14CA1BC, 0x36000700, NOP)],                      # tbz w0, #0, 0x14ca29c -> nop
}

# host: .rela.dyn entries (file offset of the entry; addend at +16) of the
# two master server tables 0x1e52b30 / 0x1e52b60, with their develified addends.
RELA = [(0xA10D8 + 24 * n, a) for n, a in enumerate(
    [0x47AE0C, 0x47AE0C, 0x3B0293, 0x3C13E6, 0x38DB19, 0x3A7A1B,     # table 0 (normal)
     0x3C13E6, 0x3C13E6, 0x3B0293, 0x47AE0C, 0x38DB19, 0x3A7A1B])]   # table 1 (China)
HOST_AT = 0x3C13E6                      # .rodata: file offset == address
HOST_DEVELIFIED = b"be01prr3mp01.cloudcell.com\0"
HOST_MAX = len(HOST_DEVELIFIED) - 1          # 26 characters
HOST2_AT = 0x47AE0C                     # second host (--mp-host2), odd table entries
HOST2_DEVELIFIED = b"0037-mp6.cloudcell.com\0"
HOST2_MAX = len(HOST2_DEVELIFIED) - 1        # 22 characters
# Master server port: (site, register) of each `mov wN, #0xea60`.
PORT_SITES = [(0xBB0F88, 3), (0xBB1020, 2), (0xBB4504, 4)]
PORT_DEVELIFIED = 60000

# stock: {version: ([(site, develified word, patched word), ...], cave address, cave words)}.
# Each version has its own slice of cave 0x1583704..0x15846a8: v1 0x1584304..0x1584350,
# v2 0x15844d4..0x158456c (v1's slice could not grow: username-v5 follows it).
# Writing one version leaves the other slice develified.
STOCK = {
    1: ([(0x1311B84, 0x9408FEC1, 0x9409C9E0),               # bl 0x1551688 -> bl 0x1584304
         (0x1311B88, 0xF9400288, NOP),                      # ldr x8, [x20] -> nop
         (0x1311B8C, 0xF9400915, NOP)],                     # ldr x21, [x8, #0x10] -> nop
        # tools/asm/rr3_omp_stock.s linked for 0x1584304 (build line in that file).
        0x1584304,
        (0xA9BF7BFD, 0x910003FD, 0x97FF34DF, 0xB0004F48, 0xF9456108, 0xF9400108, 0xB4000128,
         0xB944CD09, 0x51000D29, 0x7100153F, 0x540000A8, 0x910D2260, 0x97FF3C86, 0xAA1F03F5,
         0x14000003, 0xF9400288, 0xF9400915, 0xA8C17BFD, 0xD65F03C0)),
    # v2 (issue #325): also stock in WTT and TTC (a running game mode whose event's
    # stream is a competition LTS). tools/asm/rr3_omp_stock_v2.s linked for 0x15844d4.
    2: ([(0x1311B84, 0x9408FEC1, 0x9409CA54),               # bl 0x1551688 -> bl 0x15844d4
         (0x1311B88, 0xF9400288, NOP),
         (0x1311B8C, 0xF9400915, NOP)],
        0x15844D4,
        (0xA9BF7BFD, 0x910003FD, 0x97FF346B, 0xB0004F48, 0xF9456108, 0xF9400108, 0xB40000A8,
         0xB944CD09, 0x51000D29, 0x7100153F, 0x54000289, 0xB0004F48, 0xF942ED08, 0xF9400108,
         0xB4000288, 0x5281B109, 0x72A00029, 0xF869690A, 0xB400020A, 0x52827409, 0x72A00029,
         0xF869690A, 0xB400018A, 0xF940994A, 0xB400014A, 0xF940854A, 0xB400010A, 0xB9401140,
         0x97DAF0B2, 0x360000A0, 0x910D2260, 0x97FF3BFF, 0xAA1F03F5, 0x14000003, 0xF9400288,
         0xF9400915, 0xA8C17BFD, 0xD65F03C0)),
}
# The develified words of each stock slice (the dead function).
STOCK_CAVE_DEVELIFIED = {
    0x1584304: (
    0x79446A88, 0x79446A69, 0x6B09011F, 0x54FFC380, 0xB0FF7680, 0x91346400, 0x97EC6DBF, 0x2A1F03F5,
    0x79446E88, 0x79446E69, 0x6B09011F, 0x54FFC300, 0xB0FF7680, 0x91346400, 0x97EC6DB7, 0x2A1F03F5,
    0x912E0280, 0x912E0261, 0x97D08507),
    0x15844D4: (0xF0FF7280, 0x911B6C00, 0x97EC6D4F, 0x2A1F03F5, 0xB94EC288, 0xB94EC269, 0x6B09011F,
         0x54FFBC00, 0xB0FF7060, 0x91376800, 0x97EC6D47, 0x2A1F03F5, 0xB94EC688, 0xB94EC669,
         0x6B09011F, 0x54FFBB80, 0xD0FF74A0, 0x91101800, 0x97EC6D3F, 0x2A1F03F5, 0x397B2288,
         0x397B2269, 0x6B09011F, 0x54FFBB00, 0x90FF75C0, 0x910A3800, 0x97EC6D37, 0x2A1F03F5,
         0xB94ECE88, 0xB94ECE69, 0x6B09011F, 0x54FFBA80, 0x90FF7180, 0x91353C00, 0x97EC6D2F,
         0x2A1F03F5, 0xB94ED288, 0xB94ED269),
}
# The cave (tables/lib-code-caves.csv) requires nothing.
REQUIRES = []

# nolevel: {version: [(site, develified word, patched word), ...]}.
NOLEVEL = {1: [(0xA99CAC, 0x540001AA, 0x1400000D)]}           # b.ge 0xa99ce0 -> b 0xa99ce0

PARTS = {"nosocial": "OMP without a social log-in", "host": "OMP master server address",
         "stock": "OMP races stock (no upgrades, default tuning)",
         "nolevel": "OMP at any player level"}
DEFAULT_PARTS = ("nosocial", "host")        # stock and nolevel only when asked for


def load(path):
    data = open(path, "rb").read()
    return bytearray(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def word(d, a):
    return struct.unpack_from("<I", d, a)[0]


def nosocial_sites():
    return sorted({(s, develified) for v in NOSOCIAL.values() for s, develified, _ in v})


def nosocial_state(d):
    """0 develified, N = version N, None unrecognised."""
    if all(word(d, s) == develified for s, develified in nosocial_sites()):
        return 0
    for ver, patch in sorted(NOSOCIAL.items(), reverse=True):
        mine = {s: new for s, _, new in patch}
        if all(word(d, s) == mine.get(s, develified) for s, develified in nosocial_sites()):
            return ver
    return None


def stock_words(v):
    """[(address, word)] of stock version v (0 = develified), every stock slice included."""
    sites, cave_at, cave = STOCK.get(v, (STOCK[1][0], None, ()))
    out = [(s, new if v else develified) for s, develified, new in sites]
    for at, dev in STOCK_CAVE_DEVELIFIED.items():
        words = list(cave) if v and at == cave_at else list(dev)
        out += [(at + 4 * i, w) for i, w in enumerate(words)]
    return out


def stock_state(d):
    """0 develified, N = version N, None unrecognised."""
    for v in [0] + sorted(STOCK, reverse=True):
        if all(word(d, a) == w for a, w in stock_words(v)):
            return v
    return None


def nolevel_state(d):
    """0 develified, N = version N, None unrecognised."""
    sites = NOLEVEL[1]
    if all(word(d, s) == old for s, old, _ in sites):
        return 0
    for v, patch in sorted(NOLEVEL.items(), reverse=True):
        if all(word(d, s) == new for s, _, new in patch):
            return v
    return None


def mov_port(reg, port):
    return 0x52800000 | port << 5 | reg            # mov wN, #port


def port_state(d):
    """The port the three movs load, or None if they don't all load one."""
    ports = set()
    for site, reg in PORT_SITES:
        w = word(d, site)
        if w & 0xFFE0001F != 0x52800000 | reg:
            return None
        ports.add(w >> 5 & 0xFFFF)
    return ports.pop() if len(ports) == 1 else None


def slot_text(d, at, develified):
    """The host written in a string slot, or None (not a whole host + 0s)."""
    text = bytes(d[at:at + len(develified)])
    host = text.split(b"\0")[0]
    if host and text == host.ljust(len(develified), b"\0") and re.fullmatch(rb"[A-Za-z0-9.-]+", host):
        return host.decode()
    return None


def host_state(d):
    """'' develified, else (host, host2 or None, port); None unrecognised."""
    adds = [struct.unpack_from("<q", d, e + 16)[0] for e, _ in RELA]
    text = bytes(d[HOST_AT:HOST_AT + len(HOST_DEVELIFIED)])
    text2 = bytes(d[HOST2_AT:HOST2_AT + len(HOST2_DEVELIFIED)])
    port = port_state(d)
    if port is None:
        return None
    if adds == [a for _, a in RELA] and text == HOST_DEVELIFIED and text2 == HOST2_DEVELIFIED:
        return "" if port == PORT_DEVELIFIED else None
    host = slot_text(d, HOST_AT, HOST_DEVELIFIED)
    if host is None:
        return None
    if all(a == HOST_AT for a in adds) and text2 == HOST2_DEVELIFIED:
        return host, None, port
    host2 = slot_text(d, HOST2_AT, HOST2_DEVELIFIED)
    if host2 and adds == [HOST2_AT if n % 2 else HOST_AT for n in range(len(RELA))]:
        return host, host2, port
    return None


def host_text(h):
    host, host2, port = h
    return host + (f"/{host2}" if host2 else "") + (f":{port}" if port != PORT_DEVELIFIED else "")


def check_host(host, opt="--mp-host", most=HOST_MAX):
    if not re.fullmatch(r"[A-Za-z0-9.-]+", host or ""):
        sys.exit(f"{opt} {host!r}: use a host name or IPv4 address (letters, digits, '.', '-')")
    if len(host) > most:
        sys.exit(f"{opt} {host!r}: at most {most} characters")


def contents(d):
    """`patches` entry for rr3_build.py: '' develified, None unrecognised.
    e.g. omp=nosocial@v2+host=100.82.32.18 (only revisions carry @vN);
    with --mp-host2 and --mp-port: host=HOST/HOST2:PORT; +stock; +nolevel."""
    ns, host, st, nl = nosocial_state(d), host_state(d), stock_state(d), nolevel_state(d)
    if ns is None or host is None or st is None or nl is None:
        return None
    on = []
    if ns:
        on.append("nosocial" if ns == 1 else f"nosocial@v{ns}")
    if host:
        on.append(f"host={host_text(host)}")
    if st:
        on.append("stock" if st == 1 else f"stock@v{st}")
    if nl:
        on.append("nolevel" if nl == 1 else f"nolevel@v{nl}")
    return "omp=" + "+".join(on) if on else ""


def describe(d):
    ns, host, st, nl = nosocial_state(d), host_state(d), stock_state(d), nolevel_state(d)
    return {"nosocial": "develified" if ns == 0 else f"patched v{ns}" if ns else "unrecognised",
            "host": "develified" if host == "" else f"patched, {host_desc(host)}" if host else "unrecognised",
            "stock": "develified" if st == 0 else f"patched v{st}" if st else "unrecognised",
            "nolevel": "develified" if nl == 0 else f"patched v{nl}" if nl else "unrecognised"}


def host_desc(h):
    host, host2, port = h
    return f"{host}:{port}" + (f" (debug menu MP Server switches to {host2}:{port})" if host2 else "")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("lib")
    p = sub.add_parser("patch")
    p.add_argument("inp")
    p.add_argument("out")
    p.add_argument("--parts", default=",".join(DEFAULT_PARTS),
                   help="comma-separated: " + ", ".join(PARTS) + f" (default {','.join(DEFAULT_PARTS)})")
    p.add_argument("--stock-version", type=int, choices=sorted(STOCK), default=max(STOCK),
                   help="stock version to write (default: latest)")
    p.add_argument("--nosocial-version", type=int, choices=sorted(NOSOCIAL), default=max(NOSOCIAL),
                   help="nosocial version to write (default: latest)")
    p.add_argument("--mp-host", default="127.0.0.1",
                   help=f"master server host or IPv4 for part host (at most {HOST_MAX} characters, "
                        "default 127.0.0.1); table entries 0, 2, 4, the default one")
    p.add_argument("--mp-host2", help=f"second master server for part host (at most {HOST2_MAX} characters): "
                                      "table entries 1, 3, 5, picked with the debug menu MP Server button")
    p.add_argument("--mp-port", type=int, default=PORT_DEVELIFIED,
                   help=f"master server UDP port for part host (default {PORT_DEVELIFIED}, the develified port)")
    p.add_argument("--restore", action="store_true", help="put the develified bytes back")
    a = ap.parse_args()

    d = load(a.lib if a.cmd == "check" else a.inp)
    state = describe(d)
    for n, s in state.items():
        if s == "unrecognised":
            sys.exit(f"{n}: unexpected bytes: not the v14.0.1 develified build?")
    if a.cmd == "check":
        for n, s in state.items():
            print(f"{n} ({PARTS[n]}): {s}")
        return
    parts = [x for x in a.parts.split(",") if x]
    for n in parts:
        if n not in PARTS:
            sys.exit(f"unknown part {n}: choose from {', '.join(PARTS)}")
    if "nosocial" in parts:
        for s, develified in nosocial_sites():              # back to develified first, then the chosen version
            struct.pack_into("<I", d, s, develified)
        if not a.restore:
            for s, _, new in NOSOCIAL[a.nosocial_version]:
                struct.pack_into("<I", d, s, new)
    if "host" in parts:
        if a.restore:
            for e, add in RELA:
                struct.pack_into("<q", d, e + 16, add)
            d[HOST_AT:HOST_AT + len(HOST_DEVELIFIED)] = HOST_DEVELIFIED
            d[HOST2_AT:HOST2_AT + len(HOST2_DEVELIFIED)] = HOST2_DEVELIFIED
            for site, reg in PORT_SITES:
                struct.pack_into("<I", d, site, mov_port(reg, PORT_DEVELIFIED))
        else:
            check_host(a.mp_host)
            if a.mp_host2 is not None:
                check_host(a.mp_host2, "--mp-host2", HOST2_MAX)
            if not 1 <= a.mp_port <= 0xFFFF:
                sys.exit(f"--mp-port {a.mp_port}: 1 to 65535")
            for n, (e, _) in enumerate(RELA):
                struct.pack_into("<q", d, e + 16, HOST2_AT if a.mp_host2 and n % 2 else HOST_AT)
            d[HOST_AT:HOST_AT + len(HOST_DEVELIFIED)] = a.mp_host.encode().ljust(len(HOST_DEVELIFIED), b"\0")
            d[HOST2_AT:HOST2_AT + len(HOST2_DEVELIFIED)] = (
                a.mp_host2.encode().ljust(len(HOST2_DEVELIFIED), b"\0") if a.mp_host2 else HOST2_DEVELIFIED)
            for site, reg in PORT_SITES:
                struct.pack_into("<I", d, site, mov_port(reg, a.mp_port))
    if "stock" in parts:
        for addr, w in stock_words(0 if a.restore else a.stock_version):
            struct.pack_into("<I", d, addr, w)
    if "nolevel" in parts:
        for s, old, new in NOLEVEL[1]:
            struct.pack_into("<I", d, s, old if a.restore else new)
    out = gzip.compress(bytes(d)) if a.out.endswith(".gz") else bytes(d)
    open(a.out, "wb").write(out)
    print(f"{a.out}: " + ", ".join(f"{n} {s}" for n, s in describe(d).items()))


if __name__ == "__main__":
    main()
