#!/usr/bin/env python3
"""Online Multiplayer master server and game server for Real Racing 3
(issue #86). The game, with a lib patched by `rr3_omp.py` part host,
sends its matchmaking traffic (Firemonkeys reliable UDP, fmRUDP) to UDP
port 60000. This server:

  transport (both ports, as the lib's own server side does)
    Init (0)  version 2       -> InitAck (1) echoing the connection id
              other version   -> Abort (2), reason 0
    Data (3)  reliable        -> DataAck (4): Init id, packet sequence
    Ping (5)                  -> PingAck (6): the ping's two fields, time, 0
    DataAck (4)               -> stop resending that packet
    ClockSync (7)             -> ClockSyncAck (8): server time, ms since 1970
    Abort (2)                 -> forget the connection (and its room seat)
  master server (--port, 60000)
    message 25 (hello)        -> message 26 (game server list): one
                                 server, --game-host : --game-port
  game server (--game-port, 60001)
    19 SET_PLAYER_NAME, 29 SET_CLOUDCELL_MEMBER_ID, 4 LOBBY_CAR_CHANGED
                              -> kept for the roster
    36 JOIN_PUBLIC_ROOM       -> a seat in the room for (kind, event,
                                 league) (v0.23: the player's OMP league
                                 from rr3_cc_server.py's --omp-leagues
                                 file; a 36 before 29 waits up to 2 s)
    59 REQUEST_ROOM_PLAYER_COUNT
                              -> 59 back with the number of players in it
    a room with --min-players -> 6 LOBBY_SETTINGS to each phone (the
                                 roster: name, car, state In Lobby), then
                                 --start-delay seconds later 8
                                 LOBBY_START_RACE (the same roster).
                                 Since v0.13 with --fill-time T the room
                                 first waits up to T s for more phones,
                                 and locks at once at --max-players
    the race messages phones send, once the roster is out (v0.7; since
    v0.11 only 7, 9, 10, 12, 14, 15, 35, 54 and, since v0.12, 57, each
    at its seen size)
                              -> to every other phone of the room as 55
                                 FORWARDING_PACKET_FROM_PLAYER: 37 + the
                                 sender's slot address + the message, as
                                 reliable or unreliable as it came (the
                                 race starts on each phone only when the
                                 others' 10 FINISHED_INTRO arrive this way)
    48 REQUEST_INVITE_ROOM (v0.24, issue #427): u8 kind, u32, u32 size
                              -> 49 INVITE_ROOM: i32 room id, u8 1, u32 pass
                                 key (random): a private room for `size`
                                 phones in the host's league
    39 JOIN_RESTRICTED_ROOM (v0.24): u32 room id, u32 pass key
                              -> a seat in that private room; the race
                                 starts when it has `size` phones. Refused
                                 (wrong key, no such room, full, another
                                 league, not invited) -> 47 ROOM_UNAVAILABLE
    10 FINISHED_INTRO from every phone of the room (v0.8)
                              -> 61 SET_COUNTDOWN to each: 3d 01 + u64
                                 launch time = server ms + --countdown (the
                                 phones' clocks are our ClockSyncAck time;
                                 the start lights run the last 3 s)

Player names in the roster: the member id from message 29 looked up in
rr3_cc_server.py's data files (--members, then --names, else the in-game
username in --usernames, else "Racer" + the last 4 characters of the
player key, as on the leaderboard); without one, the name from message
19 ("Guest"). The files are only read, again whenever they change. The
member id is NOT verified: a modified game can claim another player's
id (fine for tests, not for a public server). Each player's slot gets a
made-up address 10.0.0.N:60001 (N = slot + 1) and, since v0.6, a unique
id: the member id (0x80000001 + slot without one). The game refuses a
match with two equal unique ids ("Duplicate players"); since v0.11 a
phone claiming a member id already in the room (or one of the no-member
ids) is sent as a phone without one: no member name, a slot id.

Our own Data packets are reliable: resent every second until the game
acks them (at most 10 times). Layouts and the handshake:
analysis/online-multiplayer.md, "Q2 (part)" and "Q11" sections.
--record-only answers nothing (as v0.1).

--game-host defaults to the address of this PC that the phone's packets
arrived on (found per phone with a routing lookup), e.g. the Tailscale IP.

Every datagram, received or sent, is printed as one line (number, time,
port, direction, peer, packet type and fields, master messages decoded)
and, with --save (off by default since v0.5), saved in --out (default
logs-mp/ next to this script) as
  NNNN-PORT-IP-PEERPORT.bin   a received datagram, exactly as received
and one line per datagram in log.txt (time, port, in/out, peer, size,
full hex). The packets may carry phone or account ids: keep the files
private and out of the repo. --no-save is still accepted and changes
nothing.

Checks on what phones send (issue #143, analysis/server-safety.md): a
negative car id (message 4) counts as no car; a name from message 19 is
kept only if it is 1-24 printable ASCII characters (else "Guest"); a
datagram that makes the server fail is logged and dropped, the server
keeps running. Since v0.11 (analysis/server-safety.md, "Relay review"):
only the race messages above are relayed, each at the size the phones
send it, at most --relay-rate per second per phone (others are dropped,
each kind printed once); Data, DataAck and Abort must carry the phone's
Init id (--no-id-check turns that off: the phone's Data id is not traced
in the lib); a phone silent for --idle seconds is forgotten (it no longer
holds up the race start or a room). Since v0.14 an Init from an address
that already has a connection is acked again when it carries the same id;
with a new id the old connection is forgotten first, so one phone never
counts twice in a room (issue #143, 8.3). Since v0.22 (issue #143 item
5): a lobby car (message 4) not in the game's car list (--cars, default
data/car-index.csv, a copy of the repo's tables/car-index.csv; --no-cars)
counts as no car; every roster name, the ones from rr3_cc_server.py's
files too, must pass the message 19 rule; a relayed 9 must carry the
sender's own slot and a 57 an on/off byte of 0 or 1, else it is dropped;
a 35 naming another player's slot is logged and still relayed.

Flood limits (v0.15, issue #143, 8.4): Ping and ClockSync are answered only
on a connection (the phones always send Init first, 2026-10-21/22 logs);
an Init is not answered when the server already has --max-conns
connections (default 64) or the address's IP has --max-per-ip (default 4;
phones behind one router share an IP). Datagrams from an address with no
connection that get no answer are neither printed nor saved; every 10 s
one line sums them up.

Admit file (v0.25, issue #452): --admit-file FILE, the file
rr3_cc_server.py writes with --build-admit-file. The master's hello and the
game port's Init are answered only from an IP CC admitted in the last 15
min: a sync on an allowed build and, with CC's --attest-enforce, from a
player who passed key attestation. A missing or broken file admits nobody.
The link is the IP, so phones behind one router pass together.

Blocklist (v0.21, issue #332): --blocklist (default data/blocklist.txt,
the same file rr3_cc_server.py reads; rr3_build_policy.Blocklist) refuses
`ip A.B.C.D` / `ip A.B.C.0/24` rules on both ports: their datagrams get no
answer and drop their connection (summed up every 10 s). A `member N`
rule drops a phone on the game port when its message 29 names that member
id; the master hello carries no member id, and message 29 isn't verified,
so a member rule only stops a phone that sends its own id. A missing file
blocks nobody; it is re-read when it changes.

Private rooms (v0.24, issue #427; analysis/online-multiplayer.md "OMP
invites"): the host's 48 makes a room with a random id and pass key and
gets them in 49; the host and the invited friends join with 39 (the
friend's game sends it after Confirm on an rr3://MultiplayerInvite link).
A join is refused with 47 ROOM_UNAVAILABLE (layout known; the numeric
JOIN_ERROR reasons of message 40 are not, so 40 is never sent) when the
key is wrong, the room is gone or full, the joiner's league differs from
the host's, or --invites lists the room without the joiner's member id
(no file or no entry: the pass key alone). The roster goes out when the
room is full (no --fill-time); when the host leaves before that, or after
--private-ttl seconds (default 900) without starting, the room closes and
the phones in it get 47. Open private rooms are written to
--private-rooms (default data/rr3-omp-private-rooms.json) for
rr3_cc_server.py. A phone that aborts its connection and keeps sending
Data with the same id within RECONNECT_S gets that connection back
(issue #427: the invited phone does that right after Confirm); the
"ignored" summary line now shows the first bytes of one ignored datagram.

Race Selector P2P rooms (v0.26, issue #469; docs/selector-p2p.md): a phone
with rr3_selector_p2p.py v2 joins (36) with event -1000 - 4096 * track -
16 * laps. Every negative event (the selector's; OMP events are positive)
gets a room of its own: no event +-1 merge (#280) and no league split.
When such a room locks, its members and the decoded track and laps are
written to --selector-rooms (default data/rr3-omp-selector-rooms.json;
entries older than SELECTOR_KEEP_S are dropped) for rr3_cc_server.py,
which answers that room's StartMatch with them (v5.60).

Runs on a PC (or the phone, Termux) next to rr3_cc_server.py. Open UDP
60000 and 60001 in the PC's firewall. Only the Python standard library
is used. Stop with Ctrl+C.

Usage:
  python rr3_mp_server.py [--bind 0.0.0.0] [--port 60000] [--game-port 60001]
                          [--game-host HOST] [--min-players 2] [--max-players N] [--fill-time 0]
                          [--start-delay 5] [--countdown 5000]
                          [--relay-rate 30] [--idle 30] [--no-id-check]
                          [--max-conns 64] [--max-per-ip 4]
                          [--build-allowlist FILE] [--blocklist FILE] [--admit-file FILE]
                          [--members FILE] [--usernames FILE] [--names FILE] [--cars FILE | --no-cars]
                          [--server-key FILE] [--out DIR] [--save] [--record-only]
                          [--invites FILE] [--private-rooms FILE] [--private-ttl 900]
                          [--selector-rooms FILE] [--status-file FILE] [--no-finish-release]
"""
# Server version (shown at start-up). Bump it with every change to what the
# server answers. v0.1 recorded only; v0.2 answered the fmRUDP transport;
# v0.3 answers the master server hello with a game server list and runs
# the game server port; v0.4 answers ClockSync, the room join and the
# player count, and sends the roster and the race start; v0.5 checks the
# car id and name phones send, survives a datagram that makes it fail, and
# saves datagrams only with --save (issue #143); v0.6 sends each player's
# unique id (flag bit 9, the member id) in the roster; v0.7 relays each
# phone's lobby and race messages to the other phones of its room (msg 55);
# v0.8 sends the start time (61 SET_COUNTDOWN) once every phone is in;
# v0.9 gives every player a grid position in the roster (flag bit 22);
# v0.10 counts grid positions from 1 (pole), as the game does (0xa3f5b4);
# v0.11 relays only known race messages (sizes checked, rate limited),
# checks the connection id, sends a duplicate member id as no member and
# forgets silent phones (issue #143, relay review); v0.12 also relays 57
# GAME_PLAYER_PENALISED (6 bytes), sent by the phones on 2026-10-21;
# v0.13 can wait for more phones before locking a room (--max-players,
# --fill-time; the defaults keep v0.12's rooms); v0.14 handles a second
# Init from one address: the same id is acked again, a new id first
# forgets the old connection, an address joins a room once, and a phone
# that left a locked room no longer counts there (issue #143, 8.3); v0.15
# answers Ping and ClockSync only on a connection, caps connections
# (--max-conns, --max-per-ip) and sums up ignored datagrams instead of
# printing each one (issue #143, 8.4); v0.16 refuses room sizes over the
# game's 43 slots (issue #143, 8.6); v0.17 optionally withholds the game-
# server list unless the master hello names an allowed PRR build; v0.18
# also checks the game port: an Init is answered only from an IP whose
# master hello named an allowed build in the last 15 minutes (issue #242,
# rr3_build_policy.BuildGate shared by both ports); v0.19 puts a join
# for event e in an open room of the same kind for e-1 or e+1 when there is
# no room for e: a phone that rematches from the results screen keeps the
# race slot it raced while a phone coming from the menu has the next one,
# and the track comes from StartMatch (server time), not the event
# (issue #280, analysis/online-multiplayer.md "Rematch from the results
# screen"). The log says "merged"; v0.20 accepts iOS build labels
# `PRR iNN-channel` too (rr3_build_policy v1.2, issue #299); v0.21 refuses
# blocked addresses on both ports and a blocked member id on the game port
# (--blocklist, rr3_build_policy v1.3 Blocklist, issue #332); v0.22 checks
# what one phone sends to the others (issue #143 item 5): a msg 4 car not
# in the game's car list (--cars, default data/car-index.csv, the repo's
# tables/car-index.csv; missing file = car >= 0 only, with a warning;
# --no-cars) counts as no car; every roster name, the ones from
# rr3_cc_server.py's files too, must pass clean_name (else "Racer XXXX",
# then "Guest"); a relayed msg 9 must carry the sender's own slot and a
# msg 57 an on/off byte of 0 or 1, else it is dropped; a msg 35 naming
# another player's slot is logged (once per room) and still relayed;
# v0.23 splits rooms by OMP league (issue #264): a room is (kind, event,
# league), the league being the one rr3_cc_server.py (v5.48+) served the
# member in its last 10536 (--leagues, default data/rr3-omp-leagues.json,
# read again when it changes; no file, no member id, a member id another
# connected phone already uses, or an unknown member = league 1); a join
# (36) that arrives before the member id (29) waits up to JOIN_HOLD_S for
# it; the room count (59) counts the player's own league's room;
# v0.24 makes private rooms for OMP invites (issue #427): 48 -> 49 with a
# random room id and pass key, 39 joins (refused with 47), the race starts
# when the room is full, it closes when the host leaves or after
# --private-ttl; open rooms are written to --private-rooms; --invites
# (written by rr3_cc_server.py, phase 2) limits who may join; an aborted
# connection that keeps sending is restored within RECONNECT_S; the
# ignored-datagram summary shows a sample.
# v0.25 (#452 phase 2): --admit-file FILE (rr3_cc_server.py's
# --build-admit-file) answers the master hello and the game port's Init only
# from an IP CC admitted in the last 15 min: a sync on an allowed build and,
# with CC's --attest-enforce, a passing key attestation. MP's lobby is UDP
# and carries no token, so the phone's IP is the link. Phones behind one
# router share it. A missing or broken file admits nobody.
# v0.26 (#469 part 2): Race Selector P2P joins (negative events; with
# rr3_selector_p2p.py v2, -1000 - 4096 * track - 16 * laps) get exact rooms
# (no +-1 merge, no league split); locked selector rooms go to
# --selector-rooms (members, track, laps) for rr3_cc_server.py v5.60.
# v0.27 (#427): a private room starts only when it is full and every phone
# in it has a car (msg 4, car >= 0). The invited phone joins from the
# game's popup before car select (msg 4 car -1); v0.26 sent the roster with
# no cars and started the race, and both phones crashed (2026-11-08). A
# later msg 4 re-checks the room; the --private-ttl close still applies.
# v0.28 (#374, #542): --status-file (default data/mp-status.json) is written
# every STATUS_S seconds, atomically: counts (rooms, players in rooms,
# players still searching) and one entry per open room (public filling,
# private, locked and started; state, private flag, league, players, max,
# seconds since it was made, the member ids by the roster's rule) for
# rr3_cc_server.py's /prr/api/status and /prr/api/live. No track, no
# names, no addresses. Public rooms get a creation time when made.
# v0.29 (#614, Tom 2026-11-10, option a): phones on carrier networks
# (carrier-grade NAT) reach CC and MP, and even MP's two ports, from
# different addresses of one pool, so the exact-IP admit check refused
# them (7 addresses on release night, b54/b55-stable included). The admit
# check (master hello, game port Init) and the game port's build cache now
# also match the address range: IPv4 /24, IPv6 /64 (range_key). A match by
# range is logged ("admitted by range"). Refusal lines carry the time.
# v0.30 (#359, Tom 2026-11-11: "let the finishers just continue on towards
# the finish menu without having to wait for other opponents"): a phone
# whose player finished waits on WAITING FOR OPPONENTS (0xf36894) until
# every roster slot is finished, left or disconnected (0x12ea148), and only
# then sends FinishedMatch 10532 (analysis/online-multiplayer.md "Race end:
# what the finisher waits for"). When MP relays a real 14
# GAME_PLAYER_FINISHED_RACE (a time other than 0 and -1) from a phone, it
# now also sends that phone alone a 14 for every player of the room still
# racing (no real 14 or 15 yet, not gone), from that player's slot address,
# with time and best lap -1 (no time): the phone's parser (0xbaff50) marks
# the slot finished, the wait ends and the results come up at once, the
# players still racing with an empty time. CC takes each player's own
# report at settle, so the results stay theirs. --no-finish-release turns
# it off.
VERSION = "0.30"

import argparse
import csv
import datetime
import ipaddress
import json
import os
import re
import secrets
import select
import socket
import struct
import sys
import time

from rr3_build_policy import AdmitFile, Blocklist, BuildAllowlist, BuildGate, BUILD_TAG_TEXT_RE, \
    ip_key as policy_ip_key

# fmRUDP packet types: the first byte (dispatcher 0x1467e34).
INIT, INIT_ACK, ABORT, DATA, DATA_ACK, PING, PING_ACK, CLOCK_SYNC, CLOCK_SYNC_ACK, BROADCAST = range(10)
NAMES = ["Init", "InitAck", "Abort", "Data", "DataAck", "Ping", "PingAck", "ClockSync",
         "ClockSyncAck", "BroadcastDiscovery"]
VERSION_RUDP = 2                # InitPacket version the lib accepts (0x14687bc)
RELIABLE = 0x04                 # DataPacket flags bit 2 (0x146bd08)
OUR_FLAGS = 0x07                # flags the phone uses on its Data packets
ABORT_BAD_VERSION = 0           # Abort reasons (0x1468bf8, 0x1469910, 0x1468b38)
RESEND_S, RESEND_MAX = 1.0, 10
JOIN_HOLD_S = 2.0               # a 36 before its 29 waits this long for the member id (v0.23, #264)
PRIVATE_TTL_S = 15 * 60         # a private room not started by then closes (v0.24, #427; Tom: 15 min)
SELECTOR_KEEP_S = 30 * 60       # a locked selector room stays in --selector-rooms this long (v0.26, #469)
SELECTOR_LEAGUE = 0             # the league key of every selector room: no league split (v0.26)
RECONNECT_S = 10.0              # an aborted connection still sending Data within this is restored (v0.24)
STATUS_S = 10.0                 # --status-file is written this often (v0.28, #374, #542)

# Master server messages: first payload byte (parser 0xbb25bc, writer 0xbb14c8).
MSG_HELLO, MSG_GAME_SERVERS = 25, 26
# Game server messages (parser 0xbb2d98, lobby/race parser 0xbafca0).
MSG_CAR, MSG_LOBBY_SETTINGS, MSG_START_RACE, MSG_FINISHED_INTRO = 4, 6, 8, 10
MSG_SET_COUNTDOWN = 61          # 3d, u8 set, u64 launch time (handler 0xbb04b4)
MSG_PLAYER_NAME, MSG_MEMBER_ID, MSG_JOIN_PUBLIC, MSG_POINTS, MSG_PLAYER_COUNT = 19, 29, 36, 58, 59
MSG_FORWARD = 55                # FORWARDING_PACKET_FROM_PLAYER: 37, address, message (0xbb31ac)
# Private rooms (v0.24, #427): 48 u8 kind, u32, u32 size (writer 0xbb219c);
# 49 i32 room id, u8 ok, u32 pass key (dispatcher case 0xbb2f54); 39 u32 room
# id, u32 pass key (writer 0xbb205c); 47 no payload (listeners vfunc 0x20).
MSG_JOIN_RESTRICTED, MSG_ROOM_UNAVAILABLE, MSG_REQUEST_INVITE, MSG_INVITE_ROOM = 39, 47, 48, 49
# Messages relayed to the other phones of the room once the roster is out,
# with the size the phones sent them in the two-phone tests (2026-10-21/22,
# analysis/online-multiplayer.md "Test of v0.6" to "Race end"): 7 ready,
# 9 level loaded, 10 intro done, 12 position (unreliable), 14 finished,
# 15 left, 35 disconnected, 54 lap count, 57 penalty (v0.12: `39`, u8 on
# or off, u32 ms seen 500, 2000, 5000; meaning inferred). Anything else
# (server messages such as 6, 8, 30, 61) is dropped (v0.7-v0.10 relayed
# all but a few). Every other type the phones sent in the tests (logs-mp of
# 2026-10-21/22) is one the server reads itself (SERVER_READS).
RELAYED = {7: 2, 9: 5, 10: 9, 12: 32, 14: 13, 15: 5, 35: 7, 54: 7, 57: 6}
MSG_FINISHED, MSG_LEFT = 14, 15  # 14: u32 slot, u32 race time ms, u32 best lap ms (0xbac2a0); 15: u32 slot
NO_TIME = 0xFFFFFFFF            # a 14's "no time" (-1), as a phone sends when it leaves (v0.30, #359)
# Messages the server reads itself: not relayed, not reported as dropped.
SERVER_READS = {MSG_PLAYER_NAME, MSG_MEMBER_ID, MSG_CAR, MSG_JOIN_PUBLIC, MSG_POINTS, MSG_PLAYER_COUNT,
                MSG_HELLO, MSG_FORWARD, MSG_JOIN_RESTRICTED, MSG_REQUEST_INVITE}
RELAY_RATE = 30                 # relayed messages per second per phone (positions are ~4.5)
IDLE_S = 30.0                   # a phone silent this long is forgotten (keep-alives come every ~1 s)
MAX_CONNS = 64                  # connections per port at most (v0.15, #143 8.4)
ROOM_MAX = 43                   # slots the game's lobby reader takes at most (2..43, see lobby_record)
MAX_PER_IP = 4                  # connections per source IP at most (phones behind one router share it)
IGNORED_SUMMARY_S = 10.0        # how often serve() sums up ignored datagrams
UNRELIABLE_FLAGS = 0x03         # flags of the phone's GAME_POS_UPDATE packets (bit 2 clear)
# The lib's own names for them (table 0x1e52c78), for the log.
MSG_NAMES = {3: "LOBBY_TRACK_CHANGED", 4: "LOBBY_CAR_CHANGED", 5: "LOBBY_NUM_LAPS_CHANGED",
             6: "LOBBY_SETTINGS", 7: "LOBBY_PLAYER_READY", 8: "LOBBY_START_RACE",
             9: "FINISHED_LEVEL_LOADING", 10: "FINISHED_INTRO", 12: "GAME_POS_UPDATE",
             14: "GAME_PLAYER_FINISHED_RACE", 15: "GAME_PLAYER_LEFT", 18: "SERVER_FULL",
             19: "SET_PLAYER_NAME", 21: "ROOM_FULL", 22: "ROOM_JOINED", 23: "ROOM_FOUND",
             25: "REQUEST_SERVER_LIST", 26: "GAME_SERVER_LIST", 27: "SERVER_VERSION_MISMATCH",
             29: "SET_CLOUDCELL_MEMBER_ID", 30: "MATCH_REWARDS", 31: "GAME_PLAYER_PASSED_CHECKPOINT",
             32: "SERVER_MESSAGE", 33: "LOBBY_SET_MIN_TELEPORT_DISTANCE", 35: "GAME_PLAYER_DISCONNECTED",
             36: "JOIN_PUBLIC_ROOM", 38: "TOURNAMENT_PROGRESSED", 39: "JOIN_RESTRICTED_ROOM",
             40: "JOIN_ERROR", 41: "INVITE_TO_GAME", 43: "SCHEDULE_REQUEST", 44: "EVENT_SCHEDULE",
             45: "GAME_TIME_PENALTY", 46: "JOIN_SPECIFIC_ROOM", 47: "ROOM_UNAVAILABLE",
             48: "REQUEST_INVITE_ROOM", 49: "INVITE_ROOM", 51: "SERVER_QUERY_ROOM_NAME",
             52: "TOURNAMENT_JOINEDMATCH", 53: "TOURNAMENT_TOOLATE", 54: "CURRENT_LAP_COUNT",
             55: "FORWARDING_PACKET_FROM_PLAYER", 56: "GAME_PLAYER_DISQUALIFIED",
             57: "GAME_PLAYER_PENALISED", 58: "SET_CLOUDCELL_POINTS", 59: "REQUEST_ROOM_PLAYER_COUNT",
             60: "IDENTIFY_USER", 61: "SET_COUNTDOWN", 62: "GRID_POSITION", 64: "LAUNCH_GAME_AT_TIME",
             65: "CANCEL_SCHEDULED_LAUNCH", 66: "ALL_PLAYERS_IN_INTRO"}
# LOBBY_SETTINGS record (reader 0xbacd80): flag bits we send, slot states.
LOBBY_NAME, LOBBY_CAR, LOBBY_UID, LOBBY_GRID = 1 << 4, 1 << 5, 1 << 9, 1 << 22
UID_NO_MEMBER = 0x80000000      # + slot + 1: unique id of a phone without a member id
STATE_IN_LOBBY = 1              # 0 empty, 1 In Lobby, 2 Loading, 3 In Race, 4 Race Finished
SLOT_PORT = 60001               # port of the made-up slot addresses 10.0.0.N


def string(text):
    """fmRUDP string: i8 length (1-127) + bytes (0x1463944 / 0x1463714)."""
    b = text.encode()
    if not 0 < len(b) < 128:
        raise ValueError(f"string of {len(b)} bytes")
    return bytes([len(b)]) + b


def read_string(b, i):
    n = b[i]
    return b[i + 1:i + 1 + n].decode("latin-1"), i + 1 + n


def clean_name(text):
    """A name a phone sent (message 19), or None unless it is 1-24
    printable ASCII characters; it goes to every phone in the room."""
    text = (text or "").strip()
    return text if 0 < len(text) <= 24 and all(" " <= ch <= "~" for ch in text) else None


def load_cars(path):
    """The game's car ids from tables/car-index.csv (column car_id), as a
    frozenset (v0.22; as rr3_cc_server.load_cars). Raises OSError or
    ValueError."""
    with open(path, newline="") as f:
        try:
            cars = frozenset(int(r["car_id"]) for r in csv.DictReader(f))
        except KeyError as e:
            raise ValueError(f"no {e} column")
    if not cars:
        raise ValueError("no cars")
    return cars


def game_servers(host, port):
    """Message 26: one game server (more (string, u16) pairs are allowed)."""
    return bytes([MSG_GAME_SERVERS]) + string(host) + struct.pack("<H", port)


def address(ip, port):
    """fmRUDP address (reader 0x14635f0): u32 IPv4 and u16 port, both
    little-endian of the host-order value."""
    return struct.pack("<IH", struct.unpack(">I", socket.inet_aton(ip))[0], port)


def set_countdown(launch_ms):
    """Message 61 from the server: u8 1 (set), u64 launch time in the
    phones' synchronized clock (our ClockSyncAck time, Unix ms)."""
    return struct.pack("<BBQ", MSG_SET_COUNTDOWN, 1, launch_ms)


def player_count(kind, event, count):
    """Message 59 from the server: u8 kind, i32 event, i32 count."""
    return struct.pack("<BBii", MSG_PLAYER_COUNT, kind, event, count)


def selector_choice(event):
    """(track, laps) of a Race Selector P2P join from rr3_selector_p2p.py
    v2 (event = -1000 - 4096 * track - 16 * laps, env 0); None for any
    other event (OMP's, a develified selector's leftover). A v1 event
    (-1000 - 1024 * track, never in a build) can decode as laps 64 for some
    tracks."""
    if event >= -1000:
        return None
    track, rest = divmod(-1000 - event, 4096)
    laps, low = divmod(rest, 16)
    if low or not 1 <= laps <= 99:              # 99: the most rr3_race_laps.py allows
        return None
    return track, laps


def lobby_record(msg, players, me):
    """Message 6 (LOBBY_SETTINGS) or 8 (LOBBY_START_RACE): the roster, as
    the OMP phone reads it (0xbad530, lobby role 6). players = [(name, car
    or None, unique id)] in slot order, me = this phone's slot. Flags:
    names, cars when every player has one, the unique ids (bit 9, the
    slot's +0x290: the match creation refuses two slots with the same id)
    and the grid positions (bit 22, the slot's +0xac: the race puts each
    car on the grid place it names; without them both cars stayed at the
    same point off the track, 2026-10-21); grid position = slot + 1
    (v0.10: 1 = pole; 0 is no place, the v0.9 pole car was in the air).
    No launch time, track or laps (left to the game)."""
    flags = LOBBY_NAME | LOBBY_UID | LOBBY_GRID | (LOBBY_CAR if all(car is not None for _, car, _ in players) else 0)
    slots = max(2, len(players))                   # the game clamps to 2..43 (ROOM_MAX)
    out = struct.pack("<BIIbb", msg, flags, me, len(players), slots)
    for i in range(slots):
        if i >= len(players):
            out += b"\x00"                         # unused slot
            continue
        name, car, uid = players[i]
        out += b"\x01" + string(name[:24]) + b"\x01" + address(f"10.0.0.{i + 1}", SLOT_PORT)
        out += bytes([STATE_IN_LOBBY])
        if flags & LOBBY_CAR:                       # bits in the reader's order: 5 ... 9
            out += struct.pack("<I", car)
        out += struct.pack("<II", uid, i + 1)            # bit 9 unique id, then bit 22 grid position (1 = pole)
    return out


def describe_message(pay):
    """A master server message payload as text (empty when unknown)."""
    if not pay:
        return ""
    t = pay[0]
    try:
        if t == MSG_HELLO:
            proto, zero, build = struct.unpack_from("<III", pay, 1)
            text, i = read_string(pay, 13)
            rest = struct.unpack_from(f"<{(len(pay) - i) // 4}I", pay, i)
            return f"msg 25 hello: protocol {proto}, {zero}, build {build}, {text!r}, then {list(rest)}"
        if t == MSG_GAME_SERVERS:
            out, i = [], 1
            while i < len(pay):
                h, i = read_string(pay, i)
                out.append(f"{h}:{struct.unpack_from('<H', pay, i)[0]}")
                i += 2
            return "msg 26 game servers: " + ", ".join(out)
        name = f"msg {t} {MSG_NAMES[t]}" if t in MSG_NAMES else f"msg {t}"
        if t == MSG_FORWARD:
            ip = socket.inet_ntoa(struct.pack(">I", struct.unpack_from("<I", pay, 1)[0]))
            port = struct.unpack_from("<H", pay, 5)[0]
            return f"{name} from {ip}:{port}: [{describe_message(pay[7:])}]"
        if t == MSG_SET_COUNTDOWN:
            return f"{name} set {pay[1]}, launch at {struct.unpack_from('<Q', pay, 2)[0]} ms"
        if t == MSG_PLAYER_NAME:
            return f"{name} {read_string(pay, 1)[0]!r}"
        if t == MSG_MEMBER_ID:
            return f"{name} {struct.unpack_from('<I', pay, 1)[0]}"
        if t == MSG_CAR:
            return f"{name} car {struct.unpack_from('<h', pay, 1)[0]} paint {struct.unpack_from('<h', pay, 3)[0]}"
        if t == MSG_JOIN_PUBLIC:
            return f"{name} kind {pay[1]}, {struct.unpack_from('<h', pay, 2)[0]}, event {struct.unpack_from('<i', pay, 4)[0]}"
        if t == MSG_PLAYER_COUNT:
            ev = struct.unpack_from("<i", pay, 2)[0]
            cnt = f", count {struct.unpack_from('<i', pay, 6)[0]}" if len(pay) >= 10 else ""
            return f"{name} kind {pay[1]}, event {ev}{cnt}"
        if t in (MSG_LOBBY_SETTINGS, MSG_START_RACE):
            flags, me, n, slots = struct.unpack_from("<IIbb", pay, 1)
            names, i = [], 11
            for _ in range(slots):
                if not pay[i]:
                    i += 1
                    continue
                nm, i = read_string(pay, i + 1) if flags & LOBBY_NAME else ("", i + 1)
                names.append(nm)
                i += 1 + 6 + 1 + (4 if flags & LOBBY_CAR else 0) + (4 if flags & LOBBY_UID else 0) \
                    + (4 if flags & LOBBY_GRID else 0)
            return f"{name}: flags {flags:#x}, you are slot {me}, {n} players {names}, {slots} slots"
        return name
    except (struct.error, IndexError, UnicodeDecodeError):
        pass
    return f"msg {t}"


def build_tag_from_hello(pay):
    """Return the exact PRR build label in master message 25, else None."""
    if not pay or pay[0] != MSG_HELLO or len(pay) < 14:
        return None
    try:
        text, _ = read_string(pay, 13)
    except (IndexError, UnicodeError):
        return None
    labels = BUILD_TAG_TEXT_RE.findall(text)
    return labels[0] if len(labels) == 1 else None


def ip_key(addr):
    """The build gate's key for a phone: its IP (the master and game ports
    see different source ports; phones behind one router share it)."""
    return policy_ip_key(addr[0])


RANGE_V4, RANGE_V6 = 24, 64     # v0.29 (#614): admit by this range as well as by exact IP


def range_key(addr):
    """v0.29 (#614): the phone's address range, "net:" + its IPv4 /24 or
    IPv6 /64 (an IPv4-mapped IPv6 address counts as IPv4); None for a
    string that is not an address."""
    try:
        a = ipaddress.ip_address(str(addr[0]).strip())
    except ValueError:
        return None
    if a.version == 6 and a.ipv4_mapped:
        a = a.ipv4_mapped
    return "net:" + str(ipaddress.ip_network(f"{a}/{RANGE_V4 if a.version == 4 else RANGE_V6}", strict=False))


class RangeAdmitFile(AdmitFile):
    """CC's admit file, read only, with a lookup by range (v0.29, #614)."""

    def get_range(self, rkey):
        """The label of any address CC admitted within ttl_s whose
        range_key is rkey, else None."""
        if rkey is None:
            return None
        now = self.clock()
        with self._lock:
            self._load()
            items = list(self._keys.items())
        for k, (label, t) in items:
            if now - t <= self.ttl_s and k.startswith("ip:") and range_key((k[3:],)) == rkey:
                return label
        return None


def stamp():
    """The time for a [----] refusal line (v0.29), as the request lines show it."""
    return datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]


def decode(data):
    """A datagram as a dict: type, name and the fields we know."""
    if not data:
        return {"type": None, "name": "empty"}
    t = data[0]
    p = {"type": t, "name": NAMES[t] if t < len(NAMES) else f"type {t}"}
    try:
        if t == INIT and len(data) >= 9:
            p["version"], p["id"] = struct.unpack_from("<II", data, 1)
        elif t == INIT_ACK and len(data) >= 5:
            p["id"], = struct.unpack_from("<I", data, 1)
        elif t == ABORT and len(data) >= 9:
            p["reason"], p["id"] = struct.unpack_from("<II", data, 1)
        elif t == DATA and len(data) >= 10:
            p["id"], p["flags"], p["seq"] = struct.unpack_from("<IBI", data, 1)
            p["payload"] = data[10:]
        elif t in (DATA_ACK, PING) and len(data) >= 9:
            p["a"], p["b"] = struct.unpack_from("<II", data, 1)
        elif t == PING_ACK and len(data) >= 17:
            p["a"], p["b"], p["c"], p["d"] = struct.unpack_from("<IIII", data, 1)
        elif t == CLOCK_SYNC_ACK and len(data) >= 9:
            p["time"], = struct.unpack_from("<Q", data, 1)
    except struct.error:
        pass
    return p


def describe(p):
    """Fields of a decoded packet as text."""
    if p["type"] == INIT and "id" in p:
        return f"version {p['version']} id {p['id']:#010x}"
    if p["type"] in (INIT_ACK,) and "id" in p:
        return f"id {p['id']:#010x}"
    if p["type"] == ABORT and "id" in p:
        return f"reason {p['reason']} id {p['id']:#010x}"
    if p["type"] == DATA and "seq" in p:
        pay = p["payload"]
        msg = describe_message(pay)
        return (f"id {p['id']:#010x} flags {p['flags']:#04x}{' reliable' if p['flags'] & RELIABLE else ''} "
                f"seq {p['seq']} payload {len(pay)} bytes: {pay[:32].hex(' ')}{' ...' if len(pay) > 32 else ''}"
                + (f" [{msg}]" if msg else ""))
    if p["type"] == DATA_ACK and "a" in p:
        return f"id {p['a']:#010x} seq {p['b']}"
    if p["type"] == PING and "a" in p:
        return f"{p['a']} {p['b']}"
    if p["type"] == PING_ACK and "a" in p:
        return f"{p['a']} {p['b']} {p['c']} {p['d']}"
    if p["type"] == CLOCK_SYNC_ACK and "time" in p:
        return f"server time {p['time']} ms"
    return ""


def local_address(peer):
    """This PC's address on the route to peer (no packet is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(peer)
        return s.getsockname()[0]
    finally:
        s.close()


try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from rr3_cc_server import private_player_key
except ImportError:                                 # without it, --names keys must be player keys
    private_player_key = None


class Names:
    """Leaderboard names by member id, read from rr3_cc_server.py's files
    (never written): --members {"next": .., "members": {"<player key>": id}},
    --names {"<Android id, Synergy id or player key>": "<name>"},
    --usernames {"<player key>": "<name>"}. Same order as the leaderboard
    (Times.display_name in rr3_cc_server.py); files are read again when
    they change."""

    def __init__(self, members=None, usernames=None, names=None, server_key=None):
        self.paths = {"members": members, "usernames": usernames, "names": names}
        self.server_key_path = server_key
        self.cache = {}

    def load(self, what):
        path = self.paths[what]
        if not path:
            return {}
        try:
            mtime = os.path.getmtime(path)
            if self.cache.get(what, (None,))[0] != mtime:
                self.cache[what] = (mtime, json.load(open(path)))
            return self.cache[what][1]
        except (OSError, ValueError):
            return {}

    def names_key(self, k):
        """A --names key as a player key (as Times.names_key does)."""
        kind = "a" if re.fullmatch(r"[0-9a-f]{16}", k) else "s" if re.fullmatch(r"[0-9]{8,20}", k) else None
        if kind and private_player_key and self.server_key_path:
            try:
                key = open(self.server_key_path, "rb").read()
            except OSError:
                return k
            return private_player_key(key, kind, k)
        return k

    def name(self, member_id):
        """The leaderboard name of member_id, or None if it is not a member."""
        key = {i: k for k, i in self.load("members").get("members", {}).items()}.get(member_id)
        if key is None:
            return None
        fallback = "Racer " + key[-4:]
        for k, v in self.load("names").items():
            if self.names_key(k) == key:
                return clean_name(str(v)[:24]) or clean_name(fallback)      # v0.22
        return clean_name(self.load("usernames").get(key)) or clean_name(fallback)


class Leagues:
    """OMP leagues by member id (v0.23, issue #264), read from
    rr3_cc_server.py's --omp-leagues file (never written): {"<member>":
    {"pick", "served", "at"}}; `served` is the league the member's last
    10536 had. Read again when it changes; a missing or bad file = every
    player in league 1."""

    def __init__(self, path=None):
        self.path, self.mtime, self.data = path, None, {}

    def league(self, member):
        if not self.path or member is None:
            return 1
        try:
            mtime = os.path.getmtime(self.path)
            if mtime != self.mtime:
                self.mtime, self.data = mtime, {}
                data = json.load(open(self.path))
                if isinstance(data, dict):
                    self.data = data
        except (OSError, ValueError):
            self.mtime, self.data = None, {}
        entry = self.data.get(str(member))
        served = entry.get("served") if isinstance(entry, dict) else None
        return served if served in (1, 2, 3) else 1


class Invites:
    """Who may join a private room (v0.24, issue #427), read from
    rr3_cc_server.py's invites file (phase 2; never written here):
    {"<room id>": {"members": [member ids], ...}}. Read again when it
    changes. members(room id) is None when the file or the room's entry is
    missing (then the pass key alone admits)."""

    def __init__(self, path=None):
        self.path, self.mtime, self.data = path, None, {}

    def members(self, room_id):
        if not self.path:
            return None
        try:
            mtime = os.path.getmtime(self.path)
            if mtime != self.mtime:
                self.mtime, self.data = mtime, {}
                data = json.load(open(self.path))
                if isinstance(data, dict):
                    self.data = data
        except (OSError, ValueError):
            self.mtime, self.data = None, {}
        entry = self.data.get(str(room_id))
        members = entry.get("members") if isinstance(entry, dict) else None
        if not isinstance(members, list):
            return None
        return {m for m in members if isinstance(m, int)}


class Conn:
    """One phone on one port: its Init id, our next Data sequence and our
    unacked Data packets {seq: [datagram, last send time, sends]}; on the
    game port also what it told us (name, member id, car) and its room."""

    def __init__(self, cid):
        self.id, self.seq, self.unacked = cid, 0, {}
        self.useq = 0                               # our unreliable Data sequence (not checked by the phone)
        self.name, self.member, self.car, self.room = None, None, None, None
        self.held = None                            # (kind, event, deadline) of a 36 waiting for 29 (v0.23)
        self.last = time.monotonic()                # last datagram received
        self.window, self.relayed = 0, 0            # relay rate: current second, messages in it


class Room:
    """Phones that joined one public room (kind, event, league), in join
    order."""

    def __init__(self, kind, event, league=1):
        self.kind, self.event, self.league, self.players = kind, event, league, []
        self.lobby, self.start_at, self.started = False, None, False
        self.fill_at = None                         # --fill-time deadline (monotonic), once at --min-players
        self.intro, self.launch = set(), None       # phones done with the intro; launch time sent
        self.gone = set()                           # phones that left after the room locked (v0.14)
        self.flagged = set()                        # (msg, sender) relay notes already printed (v0.22)
        self.done = set()                           # phones that sent a real 14 or a 15 (v0.30, #359)
        # private room (v0.24, #427): made by a 48, joined with 39
        self.private, self.room_id, self.pass_key, self.size = False, None, None, None
        self.waiting_cars = None                   # members a full private room waits on for a car (v0.27)
        self.owner, self.owner_addr, self.created, self.created_unix = None, None, None, None


class Server:
    """fmRUDP answers for one port. role 'master' answers the hello with
    a game server list; role 'game' runs the rooms."""

    def __init__(self, role="master", record_only=False, game_host=None, game_port=60001,
                 min_players=2, start_delay=5.0, names=None, countdown_ms=5000,
                 relay_rate=RELAY_RATE, idle_s=IDLE_S, id_check=True, max_players=None, fill_s=0.0,
                 max_conns=MAX_CONNS, max_per_ip=MAX_PER_IP, build_policy=None, blocklist=None,
                 cars=None, leagues=None, invites=None, private_path=None, private_ttl=PRIVATE_TTL_S,
                 admit=None, selector_path=None, status_path=None, release=True):
        self.role, self.record_only = role, record_only
        self.game_host, self.game_port = game_host, game_port
        self.min_players, self.start_delay = min_players, start_delay
        self.max_players = max(min_players, max_players or min_players)
        self.fill_s = fill_s
        self.countdown_ms = countdown_ms
        self.relay_rate, self.idle_s, self.id_check = relay_rate, idle_s, id_check
        self.max_conns, self.max_per_ip = max_conns, max_per_ip
        self.build_policy = build_policy
        self.blocklist = blocklist                  # rr3_build_policy.Blocklist or None (v0.21, #332)
        self.admit = admit                          # CC's AdmitFile or None (v0.25, #452)
        self.blocked_members = set()                # (addr, member) already printed
        self.dropped = set()                        # (type, size) of dropped relays already printed
        self.names = names or Names()
        self.cars = cars                            # the game's car ids (--cars, v0.22), None = any >= 0
        self.leagues = leagues                      # Leagues or None = everyone league 1 (v0.23, #264)
        self.conns = {}
        self.rooms = {}                             # (kind, event, league) -> the room still filling
        self.private = {}                           # room id -> private room not locked yet (v0.24, #427)
        self.invites = invites                      # Invites or None (v0.24)
        self.private_path, self.private_ttl = private_path, private_ttl
        self.aborted = {}                           # addr -> (Conn, monotonic time) for RECONNECT_S (v0.24)
        self.selector_path = selector_path          # --selector-rooms (v0.26, #469)
        self.selector_rooms = self.load_selector()  # "<created>-<n>" -> locked selector room
        self.selector_seq = 0
        self.status_path, self.status_at = status_path, 0.0     # --status-file (v0.28, #374, #542)
        self.release = release                      # v0.30 (#359): finish_release on (--no-finish-release: off)
        self.pending = []                           # (addr, datagram) for tick()
        self.start = time.monotonic()

    def data(self, addr, payload, now=None):
        """A reliable Data packet to addr, remembered for resending."""
        c = self.conns[addr]
        d = struct.pack("<BIBI", DATA, c.id, OUR_FLAGS, c.seq) + payload
        c.unacked[c.seq] = [d, time.monotonic() if now is None else now, 1]
        c.seq += 1
        return d

    def unreliable(self, addr, payload):
        """An unreliable Data packet to addr: not resent; the phone checks
        the order only of reliable ones (0x1468ce0)."""
        c = self.conns[addr]
        d = struct.pack("<BIBI", DATA, c.id, UNRELIABLE_FLAGS, c.useq) + payload
        c.useq += 1
        return d

    def blocked(self, addr):
        """The blocklist rule for addr's IP, or None (v0.21, #332)."""
        return self.blocklist.ip(addr[0]) if self.blocklist else None

    def answer(self, data, addr):
        """Replies (list of datagrams) to one received datagram."""
        if self.record_only:
            return []
        if self.blocked(addr):                      # no answer, connection dropped (v0.21, #332)
            self.forget(addr, restorable=False)
            self.aborted.pop(addr, None)
            return []
        p = decode(data)
        t = p["type"]
        if t == INIT and "id" in p:
            if p["version"] != VERSION_RUDP:
                return [struct.pack("<BII", ABORT, ABORT_BAD_VERSION, p["id"])]
            old = self.conns.get(addr)
            if old and old.id == p["id"]:           # the same Init again (our InitAck lost): keep it
                old.last = time.monotonic()
                return [struct.pack("<BI", INIT_ACK, p["id"])]
            if old:                                 # a new connection on this address (v0.14, #143 8.3)
                self.forget(addr, restorable=False)
            if self.build_policy and self.role == "game":    # v0.18 (#242): admitted by the master?
                ok, build = self.build_policy.check_cached(ip_key(addr))
                if not ok and range_key(addr):      # v0.29 (#614): the master saw another address of the range
                    ok, build = self.build_policy.check_cached(range_key(addr))
                    if ok:
                        print(f"[----] {stamp()} OMP game port: build {build} for {addr[0]} admitted by range "
                              f"({range_key(addr)[4:]})", flush=True)
                if not ok:
                    print(f"[----] {stamp()} OMP game port denied build {build or 'unknown'} from {addr[0]}",
                          flush=True)
                    return []
            if self.admit is not None and self.role == "game" and self.admitted(addr, "game port") is None:
                print(f"[----] {stamp()} OMP game port denied {addr[0]}: not admitted by CC "
                      "(no allowed, attested sync from this IP or its range in the last 15 min)", flush=True)
                return []                           # v0.25 (#452)
            if (len(self.conns) >= self.max_conns
                    or sum(1 for a in self.conns if a[0] == addr[0]) >= self.max_per_ip):
                return []                           # full: no answer (v0.15, #143 8.4)
            self.conns[addr] = Conn(p["id"])
            return [struct.pack("<BI", INIT_ACK, p["id"])]
        c = self.conns.get(addr)
        if c is None and t == DATA and self.role == "game" and addr in self.aborted:
            old, at = self.aborted[addr]            # v0.24 (#427): the phone still uses it
            if p.get("id") == old.id and time.monotonic() - at <= RECONNECT_S:
                del self.aborted[addr]
                old.room, old.held, old.unacked = None, None, {}
                old.last = time.monotonic()
                c = self.conns[addr] = old
                print(f"[----] OMP game port: {addr[0]}:{addr[1]} sent Data on its aborted connection "
                      f"0x{old.id:08x}: restored (issue #427)", flush=True)
        if c and self.id_check:
            got = p.get("id", p.get("a")) if t in (DATA, DATA_ACK, ABORT) else c.id
            if got is not None and got != c.id:
                return []                           # not this phone's connection (v0.11)
        if c:
            c.last = time.monotonic()
        if t == DATA and "seq" in p:
            out = []
            if p["flags"] & RELIABLE:
                out.append(struct.pack("<BII", DATA_ACK, c.id if c else p["id"], p["seq"]))
            pay = p["payload"]
            if c and self.role == "master" and pay[:1] == bytes([MSG_HELLO]):
                build = build_tag_from_hello(pay)
                if self.build_policy and not self.build_policy.check(ip_key(addr), build, True)[0]:
                    print(f"[----] {stamp()} OMP master denied build {build or 'unknown'} from {addr[0]}",
                          flush=True)
                    self.forget(addr, restorable=False)
                elif self.admit is not None and self.admitted(addr, "master") is None:    # v0.25 (#452)
                    print(f"[----] {stamp()} OMP master denied {addr[0]} (build {build or 'unknown'}): not admitted "
                          "by CC (no allowed, attested sync from this IP or its range in the last 15 min)",
                          flush=True)
                    self.forget(addr, restorable=False)
                else:
                    if self.build_policy and range_key(addr):   # v0.29 (#614): for the game port's range match
                        self.build_policy.remember(range_key(addr), build)
                    host = self.game_host or local_address(addr)
                    out.append(self.data(addr, game_servers(host, self.game_port)))
            if c and self.role == "game" and pay:
                try:
                    out += self.game_message(addr, c, pay)
                except (struct.error, IndexError, ValueError):
                    pass                            # too short or bad: logged, not answered
                self.relay(addr, c, pay, p["flags"] & RELIABLE)
            return out
        if t == DATA_ACK and "b" in p and c:
            c.unacked.pop(p["b"], None)
            return []
        if t in (PING, CLOCK_SYNC) and not c:
            return []                               # only on a connection (v0.15, #143 8.4)
        if t == PING and "a" in p:
            now = int((time.monotonic() - self.start) * 1000) & 0xFFFFFFFF
            return [struct.pack("<BIIII", PING_ACK, p["a"], p["b"], now, 0)]
        if t == CLOCK_SYNC:
            return [struct.pack("<BQ", CLOCK_SYNC_ACK, int(time.time() * 1000))]
        if t == ABORT:
            self.forget(addr)
        return []

    def admitted(self, addr, port):
        """v0.25 (#452): the build label CC admitted addr with, else None.
        v0.29 (#614): an address in the range of one CC admitted counts too
        (logged as "admitted by range")."""
        label = self.admit.get(ip_key(addr))
        if label is not None or not hasattr(self.admit, "get_range"):
            return label
        label = self.admit.get_range(range_key(addr))
        if label is not None:
            print(f"[----] {stamp()} OMP {port}: {addr[0]} admitted by range ({range_key(addr)[4:]}, {label})",
                  flush=True)
        return label

    def forget(self, addr, restorable=True):
        """Drop a phone (Abort, or silent for --idle seconds): out of a room
        still filling (an empty one is deleted); a started room no longer
        waits for its intro. v0.24: a restorable connection (the phone's own
        Abort or silence, never a server-side drop such as the blocklist)
        comes back if the phone keeps sending Data with its id within
        RECONNECT_S."""
        c = self.conns.pop(addr, None)
        if c and self.role == "game" and restorable:
            if len(self.aborted) > 1000:
                self.aborted.clear()
            self.aborted[addr] = (c, time.monotonic())
        room = c.room if c else None
        if not room:
            return
        if not room.lobby:
            self.leave(room, addr)
            return
        room.gone.add(addr)                         # locked room: no longer counts there (v0.14)
        if room.started and room.launch is None and room.intro:
            for a, d in self.countdown(room):
                self.pending.append((a, d))

    def game_message(self, addr, c, pay):
        """Replies to one game server message; other phones' messages go
        to self.pending."""
        t = pay[0]
        if t == MSG_PLAYER_NAME:
            c.name = clean_name(read_string(pay, 1)[0])
        elif t == MSG_MEMBER_ID:
            c.member = struct.unpack_from("<I", pay, 1)[0]
            rule = self.blocklist.member(c.member) if self.blocklist else None
            if rule:                                # v0.21 (#332): dropped, as if it left
                if (addr, c.member) not in self.blocked_members:
                    if len(self.blocked_members) > 1000:
                        self.blocked_members.clear()
                    self.blocked_members.add((addr, c.member))
                    print(f"[----] {stamp()} OMP game port: blocked ({rule}) from {addr[0]}:{addr[1]}, dropped",
                          flush=True)
                self.forget(addr, restorable=False)
                return []
            if c.held:                              # its 36 came first (v0.23): place it now
                kind, event, _deadline = c.held
                c.held = None
                return self.join(addr, c, kind, event)
        elif t == MSG_CAR:
            car = struct.unpack_from("<h", pay, 1)[0]
            c.car = car if car >= 0 else None           # -1 stopped v0.4 (issue #143)
            if c.car is not None and self.cars is not None and c.car not in self.cars:
                print(f"[----] OMP car {car} from {addr[0]}:{addr[1]} is not in the car list: "
                      "sent as no car", flush=True)
                c.car = None                            # v0.22 (#143 item 5)
            if c.room is not None and c.room.private and not c.room.lobby:
                return self.fill(c.room, addr)          # v0.27 (#427): its car may complete the room
        elif t == MSG_JOIN_PUBLIC:
            kind, event = pay[1], struct.unpack_from("<i", pay, 4)[0]
            if c.member is None and self.leagues is not None:
                c.held = (kind, event, time.monotonic() + JOIN_HOLD_S)   # wait for 29 (v0.23)
                return []
            c.held = None
            return self.join(addr, c, kind, event)
        elif t == MSG_REQUEST_INVITE:
            kind, _a, size = pay[1], *struct.unpack_from("<II", pay, 2)
            return self.make_private(addr, c, kind, size)
        elif t == MSG_JOIN_RESTRICTED:
            room_id, key = struct.unpack_from("<II", pay, 1)
            return self.join_private(addr, c, room_id, key)
        elif t == MSG_PLAYER_COUNT and c.room and c.room.private:
            kind, event = pay[1], struct.unpack_from("<i", pay, 2)[0]
            return [self.data(addr, player_count(kind, event, len(c.room.players)))]
        elif t == MSG_PLAYER_COUNT:
            kind, event = pay[1], struct.unpack_from("<i", pay, 2)[0]
            near = (c.room and c.room.kind == kind
                    and (c.room.event == event if event < 0 else abs(c.room.event - event) <= 1)
                    and c.room.league == self.room_league(addr, c, event))
            room = c.room if near else self.find_room(kind, event, self.room_league(addr, c, event))
            return [self.data(addr, player_count(kind, event, len(room.players) if room else 0))]
        elif t == MSG_FINISHED_INTRO and c.room and c.room.started:
            return self.intro_done(addr, c.room)
        return []

    def league_of(self, addr, c):
        """The phone's OMP league (v0.23, #264): its member id's served
        league; league 1 without one, or when another connected phone
        already claims the same member id (as the roster's v0.11 rule)."""
        if self.leagues is None or c.member is None:
            return 1
        if any(o.member == c.member for a, o in self.conns.items() if a != addr):
            return 1
        return self.leagues.league(c.member)

    def room_league(self, addr, c, event):
        """The league part of a public room's key: the phone's league, or
        SELECTOR_LEAGUE for a selector join (negative event, v0.26)."""
        return SELECTOR_LEAGUE if event < 0 else self.league_of(addr, c)

    def load_selector(self):
        """The selector rooms already in --selector-rooms (kept across a
        restart); {} without the file."""
        if not self.selector_path:
            return {}
        try:
            data = json.load(open(self.selector_path))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def save_selector(self, room, now=None):
        """A locked selector room to --selector-rooms (v0.26, #469):
        {"<created>-<n>": {"members", "track", "laps", "event", "created"}};
        entries older than SELECTOR_KEEP_S are dropped. Only rooms whose
        event decodes (rr3_selector_p2p.py v2); a write error is printed,
        never fatal."""
        choice = selector_choice(room.event)
        now = int(time.time() if now is None else now)
        members = [self.conns[a].member for a in room.players if a in self.conns]
        print(f"[----] OMP selector room (event {room.event}"
              + (f": track {choice[0]}, laps {choice[1]}" if choice else ", not a v2 selector event")
              + f") locked with {len(room.players)} player(s), members "
              + ", ".join(str(m) for m in members), flush=True)
        if not self.selector_path or not choice:
            return
        self.selector_seq += 1
        self.selector_rooms = {k: v for k, v in self.selector_rooms.items()
                               if isinstance(v, dict) and now - v.get("created", 0) <= SELECTOR_KEEP_S}
        self.selector_rooms[f"{now}-{self.selector_seq}"] = {
            "members": [m for m in members if m is not None], "track": choice[0], "laps": choice[1],
            "event": room.event, "created": now}
        try:
            tmp = self.selector_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.selector_rooms, f, indent=1, sort_keys=True)
            os.replace(tmp, self.selector_path)
        except OSError as e:
            print(f"[----] could not write {self.selector_path}: {e}", flush=True)

    def make_private(self, addr, c, kind, size, now=None):
        """48 (v0.24, #427): a private room for `size` phones (host
        included) in the host's league; 49 with its id and pass key, or
        with ok 0 for a size the game can't seat."""
        if not 2 <= size <= ROOM_MAX:
            print(f"[----] OMP invite room refused: size {size} from {addr[0]}:{addr[1]}", flush=True)
            return [self.data(addr, struct.pack("<BiBI", MSG_INVITE_ROOM, 0, 0, 0))]
        for old in [r for r in self.private.values() if r.owner_addr == addr]:
            self.close_private(old, "the host asked for a new one")
        room = Room(kind, 0, self.league_of(addr, c))
        room.private, room.size, room.owner, room.owner_addr = True, size, c.member, addr
        room.created = time.monotonic() if now is None else now
        room.created_unix = int(time.time())
        while True:
            room.room_id = secrets.randbelow(0x7FFFFFFE) + 1
            if room.room_id not in self.private:
                break
        room.pass_key = secrets.randbelow(0xFFFFFFFE) + 1
        self.private[room.room_id] = room
        print(f"[----] OMP invite room {room.room_id} for {size} phone(s), league {room.league}, host "
              f"member {c.member} ({addr[0]}:{addr[1]})", flush=True)
        self.save_private()
        return [self.data(addr, struct.pack("<BiBI", MSG_INVITE_ROOM, room.room_id, 1, room.pass_key))]

    def join_private(self, addr, c, room_id, key):
        """39 (v0.24, #427): a seat in a private room, or 47."""
        room = self.private.get(room_id)
        why = None
        if room is None:
            why = "no such room (closed, started or never made)"
        elif key != room.pass_key:
            why = "wrong pass key"
        elif addr not in room.players and len(room.players) >= room.size:
            why = "room full"
        elif self.league_of(addr, c) != room.league:
            why = f"league {self.league_of(addr, c)}, the room is league {room.league}"
        elif addr != room.owner_addr:
            allowed = self.invites.members(room_id) if self.invites else None
            if allowed is not None and c.member not in allowed:
                why = f"member {c.member} not invited"
        if why:
            print(f"[----] OMP invite room {room_id}: join from {addr[0]}:{addr[1]} (member {c.member}) "
                  f"refused: {why}", flush=True)
            return [self.data(addr, bytes([MSG_ROOM_UNAVAILABLE]))]
        if c.room is not room:
            if c.room and not c.room.lobby:
                self.leave(c.room, addr)
            c.room = room
            if addr not in room.players:
                room.players.append(addr)
        print(f"[----] OMP invite room {room_id}: member {c.member} joined "
              f"({len(room.players)}/{room.size})", flush=True)
        self.save_private()
        return self.fill(room, addr)

    def close_private(self, room, why):
        """Close a private room still filling: 47 to the phones in it."""
        self.private.pop(room.room_id, None)
        for a in list(room.players):
            c = self.conns.get(a)
            if c and c.room is room:
                c.room = None
                self.pending.append((a, self.data(a, bytes([MSG_ROOM_UNAVAILABLE]))))
        room.players = []
        print(f"[----] OMP invite room {room.room_id} closed: {why}", flush=True)
        self.save_private()

    def save_private(self):
        """Write the open private rooms for rr3_cc_server.py (v0.24, #427):
        {"<room id>": {"kind", "size", "league", "owner", "members",
        "created"}}. Nothing without --private-rooms; a write error is
        printed, never fatal."""
        if not self.private_path:
            return
        data = {str(r.room_id): {"kind": r.kind, "size": r.size, "league": r.league, "owner": r.owner,
                                 "members": [self.conns[a].member for a in r.players if a in self.conns],
                                 "created": r.created_unix}
                for r in self.private.values()}
        try:
            tmp = self.private_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(data, f, indent=1, sort_keys=True)
            os.replace(tmp, self.private_path)
        except OSError as e:
            print(f"[----] could not write {self.private_path}: {e}", flush=True)

    def join(self, addr, c, kind, event):
        """Seat the phone in the open room of (kind, event, its league);
        a selector join (negative event) in the room of exactly that event,
        any league (v0.26)."""
        league = self.room_league(addr, c, event)
        room = self.find_room(kind, event, league)
        if room is None:
            room = self.rooms[(kind, event, league)] = Room(kind, event, league)
            room.created = time.monotonic()         # for --status-file's seconds (v0.28, #542)
        elif room.event != event:
            print(f"[----] OMP join for event {event} merged into the open room of event {room.event} "
                  f"(kind {kind}, league {league}, {len(room.players)} player(s); issue #280)", flush=True)
        if c.room is not room:
            if c.room and not c.room.lobby:
                self.leave(c.room, addr)
            c.room = room
            if addr not in room.players:        # never twice (v0.14, #143 8.3)
                room.players.append(addr)
        return self.fill(room, addr)

    def intro_done(self, addr, room):
        """When every phone of the room still connected has sent 10, the
        launch time to each (once): reliable 61, to addr returned, the
        others to pending."""
        room.intro.add(addr)
        out = []
        for a, d in self.countdown(room):
            if a == addr:
                out.append(d)
            else:
                self.pending.append((a, d))
        return out

    def countdown(self, room):
        """(addr, 61) for each phone of the room once all still connected
        are done with the intro; [] before that or when already sent."""
        live = self.live(room)
        if room.launch is not None or not live or not set(live) <= room.intro:
            return []
        room.launch = int(time.time() * 1000) + self.countdown_ms
        msg = set_countdown(room.launch)
        return [(a, self.data(a, msg)) for a in live]

    def relay(self, addr, c, pay, reliable):
        """Message 55 with pay to every other phone of the room, once its
        roster is out: 37 + the sender's slot address (10.0.0.N:60001, as in
        the roster) + pay; to self.pending."""
        room = c.room
        if not room or not room.lobby or addr not in room.players or addr in room.gone:
            return
        if RELAYED.get(pay[0]) != len(pay):
            if pay[0] not in SERVER_READS and (pay[0], len(pay)) not in self.dropped:  # print each kind once
                self.dropped.add((pay[0], len(pay)))
                print(f"[----] not relayed: msg {pay[0]} of {len(pay)} bytes (not a known race "
                      "message of that size)", flush=True)
            return
        slot = room.players.index(addr)
        why = self.relay_problem(room, addr, slot, pay)
        if why:
            if (pay[0], addr) not in room.flagged:  # print once per message type and phone
                room.flagged.add((pay[0], addr))
                print(f"[----] not relayed: msg {pay[0]} from {addr[0]}:{addr[1]} (slot {slot}): {why}",
                      flush=True)
            return
        second = int(time.monotonic())
        if c.window != second:
            c.window, c.relayed = second, 0
        c.relayed += 1
        if c.relayed > self.relay_rate:
            return
        fwd = bytes([MSG_FORWARD]) + address(f"10.0.0.{slot + 1}", SLOT_PORT) + pay
        for a in self.live(room):
            if a != addr:
                self.pending.append((a, self.data(a, fwd) if reliable else self.unreliable(a, fwd)))
        self.finish_release(room, addr, slot, pay)

    def finish_release(self, room, addr, slot, pay):
        """v0.30 (#359): after a real 14 (finished: a time other than 0 and
        -1) from addr, send addr alone a 14 with no time for every other
        player of the room still racing, so its race-end wait ends. A 15
        (left) or a real 14 marks the sender done; a quitter's 14 (time 0)
        does neither."""
        if pay[0] == MSG_LEFT:
            room.done.add(addr)
            return
        if pay[0] != MSG_FINISHED or struct.unpack_from("<I", pay, 5)[0] in (0, NO_TIME):
            return
        room.done.add(addr)
        if not self.release:
            return
        racing = [i for i, a in enumerate(room.players)
                  if a != addr and a not in room.done and a not in room.gone]
        for i in racing:
            msg = struct.pack("<BIII", MSG_FINISHED, i, NO_TIME, NO_TIME)
            self.pending.append((addr, self.data(addr, bytes([MSG_FORWARD]) + address(f"10.0.0.{i + 1}", SLOT_PORT)
                                                 + msg)))
        if racing:
            print(f"[----] OMP race end: slot {slot} ({addr[0]}:{addr[1]}) finished; sent it slot(s) "
                  f"{', '.join(map(str, racing))} as finished with no time (still racing), v0.30", flush=True)

    def relay_problem(self, room, addr, slot, pay):
        """v0.22 (issue #143 item 5): why a race message of the right type
        and size must not be relayed, or None. Only fields whose meaning is
        known are checked: 9 FINISHED_LEVEL_LOADING carries the sender's
        slot (u32), 57 GAME_PLAYER_PENALISED an on/off byte. 35
        GAME_PLAYER_DISCONNECTED naming another slot is only logged (once
        per room and phone) until an in-game test shows phones never do
        that (issue #259); 12, 14 and 54 are not decoded."""
        t = pay[0]
        if t == 9 and struct.unpack_from("<I", pay, 1)[0] != slot:
            return f"slot {struct.unpack_from('<I', pay, 1)[0]}, not the sender's {slot}"
        if t == 57 and pay[1] > 1:
            return f"on/off byte {pay[1]}"
        if t == 35 and pay[1:7] != address(f"10.0.0.{slot + 1}", SLOT_PORT) and (35, addr) not in room.flagged:
            room.flagged.add((35, addr))
            ip, port = struct.unpack_from("<IH", pay, 1)
            print(f"[----] relayed: msg 35 from {addr[0]}:{addr[1]} (slot {slot}) names "
                  f"{socket.inet_ntoa(struct.pack('>I', ip))}:{port}, not its own slot (log only, "
                  "issue #143 item 5)", flush=True)
        return None

    def player(self, addr, slot, taken=()):
        """(name, car, unique id) of a phone in the roster; the unique id is
        its member id (not verified, see above), else UID_NO_MEMBER + slot +
        1. A member id in taken (already in the room) or in the no-member
        range counts as none (v0.11), so no two slots share an id."""
        c = self.conns[addr]
        member = c.member if c.member is not None and c.member < UID_NO_MEMBER and c.member not in taken else None
        name = clean_name(self.names.name(member) if member is not None else None) or c.name or "Guest"
        return name, c.car, member if member is not None else UID_NO_MEMBER + slot + 1

    def roster(self, room, msg):
        """(addr, datagram) of message 6 or 8 for every phone in room."""
        players = []
        for i, a in enumerate(room.players):
            players.append(self.player(a, i, {uid for _, _, uid in players}))
        return [(a, self.data(a, lobby_record(msg, players, i))) for i, a in enumerate(room.players)]

    def live(self, room):
        """The room's phones still connected and not gone (v0.14)."""
        return [a for a in room.players if a in self.conns and a not in room.gone]

    def find_room(self, kind, event, league=1):
        """The open room for (kind, event, league); else (v0.19, #280) the
        open room for event - 1 or event + 1 of the same league, the
        fuller one first; None if none."""
        room = self.rooms.get((kind, event, league))
        if room is not None or event < 0:           # selector rooms: exactly their event (v0.26, #469)
            return room
        near = [r for r in (self.rooms.get((kind, event - 1, league)), self.rooms.get((kind, event + 1, league)))
                if r]
        return max(near, key=lambda r: len(r.players)) if near else None

    def leave(self, room, addr):
        """A phone leaves a room still filling: below --min-players the
        --fill-time wait stops; an empty room is deleted."""
        if room.private:                            # v0.24 (#427)
            if addr == room.owner_addr:
                if addr in room.players:
                    room.players.remove(addr)
                self.close_private(room, "the host left")
            elif addr in room.players:
                room.players.remove(addr)
                self.save_private()
            return
        if addr in room.players:
            room.players.remove(addr)
        if len(room.players) < self.min_players:
            room.fill_at = None
        if not room.players and self.rooms.get((room.kind, room.event, room.league)) is room:
            del self.rooms[(room.kind, room.event, room.league)]

    def fill(self, room, addr, now=None):
        """A phone joined: lock the room at --max-players, or at
        --min-players when there is no --fill-time; else start the
        --fill-time wait (tick() locks the room when it runs out)."""
        n = len(room.players)
        if room.private:                            # v0.24 (#427): wait for every invited phone
            if room.lobby or n < room.size:
                return []
            carless = [self.conns[a].member for a in room.players
                       if a in self.conns and self.conns[a].car is None]
            if carless:                             # v0.27 (#427): and for every car
                if carless != room.waiting_cars:
                    room.waiting_cars = carless
                    print(f"[----] OMP invite room {room.room_id}: full, waiting for a car from member(s) "
                          f"{', '.join(str(m) for m in carless)}", flush=True)
                return []
            return self.lock(room, addr)
        if room.lobby or n < self.min_players:
            return []
        if n < self.max_players and self.fill_s > 0:
            if room.fill_at is None:
                room.fill_at = (time.monotonic() if now is None else now) + self.fill_s
            return []
        return self.lock(room, addr)

    def lock(self, room, addr=None):
        """The roster to every phone (the one in addr returned, the others
        to pending) and the race start timer; the next phone gets a new
        room."""
        room.lobby = True
        room.start_at = time.monotonic() + self.start_delay
        if room.private:                            # v0.24 (#427): no more joins
            self.private.pop(room.room_id, None)
            print(f"[----] OMP invite room {room.room_id} full ({len(room.players)}): roster sent", flush=True)
            self.save_private()
        else:
            del self.rooms[(room.kind, room.event, room.league)]     # the next phone gets a new room
            if room.event < 0:
                self.save_selector(room)            # v0.26 (#469): for rr3_cc_server.py's StartMatch
        out = []
        for a, d in self.roster(room, MSG_LOBBY_SETTINGS):
            if a == addr:
                out.append(d)
            else:
                self.pending.append((a, d))
        return out

    def tick(self, now=None):
        """(addr, datagram) due now: other phones' messages, race starts,
        resends."""
        now_m = time.monotonic() if now is None else now
        for addr in [a for a, c in self.conns.items() if now_m - c.last > self.idle_s]:
            self.forget(addr)
        for addr, c in [(a, c) for a, c in self.conns.items() if c.held and now_m >= c.held[2]]:
            kind, event, _deadline = c.held          # no 29 in time (v0.23): league 1
            c.held = None
            print(f"[----] OMP join from {addr[0]}:{addr[1]} without a member id after {JOIN_HOLD_S:g} s: "
                  "league 1", flush=True)
            self.pending += self.join(addr, c, kind, event)
        for room in [r for r in self.rooms.values() if r.fill_at is not None and now_m >= r.fill_at]:
            self.pending += self.lock(room)
        for room in [r for r in self.private.values() if now_m - r.created >= self.private_ttl]:
            self.close_private(room, f"not full after {self.private_ttl:g} s")
        for addr in [a for a, (_c, at) in self.aborted.items() if now_m - at > RECONNECT_S]:
            del self.aborted[addr]
        out, self.pending = self.pending, []
        for room in {id(c.room): c.room for c in self.conns.values() if c.room}.values():
            if room.lobby and not room.started and now_m >= room.start_at:
                room.started = True
                room.players = self.live(room)
                if room.players:
                    out += self.roster(room, MSG_START_RACE)
        if self.status_path and now_m >= self.status_at:
            self.status_at = now_m + STATUS_S
            self.save_status(now_m)
        return out + self.resends(now)

    def open_rooms(self):
        """Every room with a phone in it (v0.28, #542): the public rooms
        still filling, the private ones, and the locked or started rooms,
        which are in neither dict and only reachable from the phones."""
        rooms = {id(r): r for r in list(self.rooms.values()) + list(self.private.values())}
        for c in self.conns.values():
            if c.room is not None:
                rooms.setdefault(id(c.room), c.room)
        return [r for r in rooms.values() if self.live(r)]

    def status(self, now=None):
        """--status-file's contents (v0.28, #374, #542): counts and one
        entry per open room. Member ids by the roster's rule (player()): an
        id already in the room or in the no-member range is left out. No
        names, addresses, connection ids or tracks."""
        now_m = time.monotonic() if now is None else now
        rooms, searching = [], sum(1 for c in self.conns.values() if c.held)
        for r in self.open_rooms():
            live = self.live(r)
            members = []
            for a in live:
                m = self.conns[a].member
                if m is not None and 0 <= m < UID_NO_MEMBER and m not in members:
                    members.append(m)
            state = "started" if r.started else "locked" if r.lobby else "filling"
            if state == "filling":
                searching += len(live)
            created = r.created if r.created is not None else now_m
            rooms.append({"state": state, "private": bool(r.private or r.event < 0), "league": r.league,
                          "players": len(live), "max": r.size if r.private else self.max_players,
                          "seconds": max(0, int(now_m - created)), "members": members})
        rooms.sort(key=lambda x: -x["seconds"])
        return {"version": VERSION, "updated": int(time.time()), "rooms": len(rooms),
                "in_rooms": sum(x["players"] for x in rooms), "searching": searching, "room_list": rooms}

    def save_status(self, now=None):
        """Write --status-file atomically (temp file, then rename); a write
        error is printed, never fatal."""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.status_path)), exist_ok=True)
            tmp = self.status_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.status(now), f, indent=1, sort_keys=True)
            os.replace(tmp, self.status_path)
        except OSError as e:
            print(f"[----] could not write {self.status_path}: {e}", flush=True)

    def resends(self, now=None):
        """(addr, datagram) for every unacked Data packet due again."""
        now = time.monotonic() if now is None else now
        out = []
        for addr, c in self.conns.items():
            for seq, u in list(c.unacked.items()):
                if now - u[1] >= RESEND_S:
                    if u[2] >= RESEND_MAX:
                        del c.unacked[seq]
                        continue
                    u[1], u[2] = now, u[2] + 1
                    out.append((addr, u[0]))
        return out


def line(n, now, port, way, addr, data):
    """One printed line per datagram."""
    p = decode(data)
    return (f"[{n:04d}] {now[11:]} :{port} {way} {addr[0]}:{addr[1]} {len(data)} bytes {p['name']} "
            f"{describe(p)}").rstrip()


def save(outdir, n, now, port, way, addr, data):
    """Write a received datagram and the log line of every datagram."""
    if way == "in":
        with open(os.path.join(outdir, f"{n:04d}-{port}-{addr[0]}-{addr[1]}.bin"), "wb") as f:
            f.write(data)
    with open(os.path.join(outdir, "log.txt"), "a") as f:
        f.write(f"{now} :{port} {way} {addr[0]}:{addr[1]} {len(data)} {data.hex()}\n")


def serve(socks, outdir, limit=None, linger=0.0):
    """socks: [(socket, Server)]. Receive, log and answer datagrams until
    Ctrl+C (or, for tests, `limit` received datagrams and then `linger`
    seconds more); resend our unacked Data packets. Returns how many
    datagrams were received."""
    n = got = 0
    by_fd = {s.fileno(): (s, srv) for s, srv in socks}
    ignored, ignored_from, summary_at = 0, set(), time.monotonic() + IGNORED_SUMMARY_S
    ignored_sample = None                           # v0.24 (#427): one ignored datagram, shown in the summary
    blocked, blocked_from = 0, set()

    def emit(s, srv, way, addr, d):
        nonlocal n
        n += 1
        now = datetime.datetime.now().isoformat(timespec="milliseconds")
        port = s.getsockname()[1]
        if way == "out":
            s.sendto(d, addr)
        if outdir:
            save(outdir, n, now, port, way, addr, d)
        print(line(n, now, port, "<-" if way == "in" else "->", addr, d), flush=True)

    def failed(what, e):
        # One bad datagram must never stop the server (issue #143).
        print(f"[----] {what} failed, dropped: {type(e).__name__}: {e}", flush=True)

    end = None
    while end is None or time.monotonic() < end:
        if limit is not None and got >= limit and end is None:
            end = time.monotonic() + linger
            if not linger:
                break
        ready, _, _ = select.select([s for s, _ in socks], [], [], 0.2)
        for s in ready:
            s, srv = by_fd[s.fileno()]
            try:
                data, addr = s.recvfrom(65535)
            except OSError as e:                    # e.g. Windows: ICMP port unreachable
                failed("receive", e)
                continue
            got += 1
            try:
                rule = srv.blocked(addr)
                if rule:                            # summed up, never printed one by one (v0.21, #332)
                    srv.answer(data, addr)          # drops the connection, answers nothing
                    blocked += 1
                    blocked_from.add(rule)
                    continue
                known = addr in srv.conns
                replies = srv.answer(data, addr)
                if not (replies or known or addr in srv.conns or srv.record_only):
                    ignored += 1                    # no connection, no answer: summed up (v0.15)
                    ignored_from.add(addr)
                    if ignored_sample is None:
                        ignored_sample = f"{addr[0]}:{addr[1]} {len(data)} bytes: {data[:24].hex(' ')}"
                    continue
                emit(s, srv, "in", addr, data)
                for r in replies:
                    emit(s, srv, "out", addr, r)
            except Exception as e:
                failed(f"datagram from {addr[0]}:{addr[1]}", e)
        for s, srv in socks:
            try:
                for addr, d in srv.tick():
                    emit(s, srv, "out", addr, d)
            except Exception as e:
                failed("timers", e)
        if ignored and time.monotonic() >= summary_at:
            print(f"[----] ignored {ignored} datagram(s) from {len(ignored_from)} address(es) "
                  f"with no connection (no answer); e.g. {ignored_sample}", flush=True)
            ignored, ignored_from, ignored_sample = 0, set(), None
        if blocked and time.monotonic() >= summary_at:
            print(f"[----] blocked {blocked} datagram(s) ({', '.join(sorted(blocked_from))})", flush=True)
            blocked, blocked_from = 0, set()
        if time.monotonic() >= summary_at:
            summary_at = time.monotonic() + IGNORED_SUMMARY_S
    if ignored:
        print(f"[----] ignored {ignored} datagram(s) from {len(ignored_from)} address(es) "
              f"with no connection (no answer); e.g. {ignored_sample}", flush=True)
    if blocked:
        print(f"[----] blocked {blocked} datagram(s) ({', '.join(sorted(blocked_from))})", flush=True)
    return got


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bind", default="0.0.0.0",
                    help="address to listen on (default 0.0.0.0: every network, needed for a phone)")
    ap.add_argument("--port", type=int, default=60000, help="master server UDP port (default 60000, the game's)")
    ap.add_argument("--game-port", type=int, default=60001, help="game server UDP port (default 60001)")
    ap.add_argument("--game-host", help="game server address sent to the phone (default: the address of "
                                        "this PC the phone's packets arrived on)")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs-mp"),
                    help="folder for the saved datagrams (default logs-mp/ next to this script)")
    save = ap.add_mutually_exclusive_group()
    save.add_argument("--save", action="store_true",
                      help="save every datagram in --out (they may hold phone ids); for your own tests")
    save.add_argument("--no-save", action="store_true",
                      help="only print, save nothing (the default since v0.5; kept for old command lines)")
    ap.add_argument("--record-only", action="store_true", help="answer nothing (as v0.1)")
    ap.add_argument("--min-players", type=int, default=2,
                    help="players a room needs before the roster is sent (default 2, the game's "
                         "matchmaking_min_players; 1 for a test with one phone)")
    ap.add_argument("--max-players", type=int,
                    help="a room locks at once with this many phones (default: --min-players); "
                         "with --fill-time, rooms can grow up to it")
    ap.add_argument("--fill-time", type=float, default=0.0,
                    help="seconds a room with --min-players waits for more phones, up to --max-players, "
                         "before the roster is sent (default 0: lock at --min-players, as v0.12)")
    ap.add_argument("--countdown", type=int, default=5000,
                    help="ms from the last phone's 'finished intro' to the race start (default 5000; "
                         "the lights run the last 3000)")
    ap.add_argument("--relay-rate", type=int, default=RELAY_RATE,
                    help=f"race messages relayed per second per phone, more are dropped (default {RELAY_RATE})")
    ap.add_argument("--idle", type=float, default=IDLE_S,
                    help=f"seconds without a datagram before a phone is forgotten (default {IDLE_S:g})")
    ap.add_argument("--max-conns", type=int, default=MAX_CONNS,
                    help=f"connections per port at most; a new Init past it gets no answer (default {MAX_CONNS})")
    ap.add_argument("--max-per-ip", type=int, default=MAX_PER_IP,
                    help=f"connections per source IP at most (default {MAX_PER_IP}; phones behind one router share an IP)")
    ap.add_argument("--no-id-check", action="store_true",
                    help="accept Data, DataAck and Abort whatever connection id they carry (as v0.10)")
    ap.add_argument("--build-allowlist", metavar="FILE",
                    help="on the master port, return a game-server address only for exact PRR build "
                         "labels in this UTF-8 file (one PRR bNN-channel or iOS PRR iNN-channel per line); missing/unknown "
                         "labels are denied; the game port answers an Init only from an IP the "
                         "master allowed in the last 15 minutes (v0.18); reloads about once a second")
    ap.add_argument("--blocklist", metavar="FILE",
                    default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "blocklist.txt"),
                    help="the blocklist rr3_cc_server.py reads (default data/blocklist.txt next to this "
                         "script): ip rules get no answer on either port, member rules are dropped on the "
                         "game port at message 29; re-read when it changes; a missing file blocks nobody (v0.21)")
    ap.add_argument("--start-delay", type=float, default=5.0,
                    help="seconds between the roster and the race start (default 5)")
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--cars", default=os.path.join(here, "data", "car-index.csv"), metavar="CAR_INDEX_CSV",
                    help="the game's car ids (the repo's tables/car-index.csv): a lobby car not in it "
                         "is sent as no car (v0.22; default data/car-index.csv next to this script; a "
                         "missing file only checks car >= 0)")
    ap.add_argument("--no-cars", action="store_true",
                    help="do not check lobby car ids against a car list (only car >= 0, as v0.21)")
    ap.add_argument("--members", default=os.path.join(here, "data", "rr3-members.json"),
                    help="rr3_cc_server.py's member ids file (default data/rr3-members.json next to this script)")
    ap.add_argument("--usernames", default=os.path.join(here, "data", "rr3-usernames.json"),
                    help="rr3_cc_server.py's usernames file (default data/rr3-usernames.json)")
    ap.add_argument("--names", help="the --names file given to rr3_cc_server.py, if any")
    ap.add_argument("--leagues", default=os.path.join(here, "data", "rr3-omp-leagues.json"),
                    help="rr3_cc_server.py's --omp-leagues file, only read: rooms are split by each "
                         "player's OMP league (v0.23, issue #264; default data/rr3-omp-leagues.json; "
                         "missing = everyone league 1)")
    ap.add_argument("--no-leagues", action="store_true",
                    help="one room per event for everyone, no league split (as v0.22)")
    ap.add_argument("--invites", default=os.path.join(here, "data", "rr3-omp-invites.json"),
                    help="who may join each private room, written by rr3_cc_server.py (v0.24, #427; "
                         "default data/rr3-omp-invites.json; missing = the pass key alone admits)")
    ap.add_argument("--private-rooms", default=os.path.join(here, "data", "rr3-omp-private-rooms.json"),
                    help="file this server writes with the open private rooms, for rr3_cc_server.py "
                         "(v0.24, #427; default data/rr3-omp-private-rooms.json)")
    ap.add_argument("--private-ttl", type=float, default=PRIVATE_TTL_S,
                    help=f"seconds a private room waits to be full before it closes (default {PRIVATE_TTL_S})")
    ap.add_argument("--selector-rooms", default=os.path.join(here, "data", "rr3-omp-selector-rooms.json"),
                    help="file this server writes with the locked Race Selector P2P rooms (members, track, "
                         "laps), for rr3_cc_server.py (v0.26, #469; default data/rr3-omp-selector-rooms.json)")
    ap.add_argument("--status-file", default=os.path.join(here, "data", "mp-status.json"),
                    help="file this server writes every 10 s with the room counts and open rooms "
                         "(league, players, max, seconds, member ids; no names or addresses), for "
                         "rr3_cc_server.py's /prr/api/status and /prr/api/live (v0.28, #374, #542; "
                         "default data/mp-status.json)")
    ap.add_argument("--no-finish-release", action="store_true",
                    help="v0.30 (#359): don't send a finisher the players still racing as finished with "
                         "no time (the finisher then waits for them, as before v0.30)")
    ap.add_argument("--admit-file", metavar="FILE",
                    help="rr3_cc_server.py's --build-admit-file: answer the hello and the game port only "
                         "from an IP CC admitted in the last 15 min (an allowed sync; with CC's "
                         "--attest-enforce also attested); a missing file admits nobody (v0.25, #452)")
    ap.add_argument("--server-key", default=os.path.join(here, "server.key"),
                    help="rr3_cc_server.py's server.key, only read (for --names keyed by Android or Synergy id)")
    a = ap.parse_args()
    if a.max_conns < 1 or a.max_per_ip < 1:
        sys.exit("--max-conns and --max-per-ip must be at least 1")
    if a.game_host:
        string(a.game_host)                         # fails early if too long
    if a.min_players < 1 or (a.max_players is not None and a.max_players < a.min_players):
        ap.error("--min-players must be 1 or more and --max-players at least --min-players")
    if max(a.min_players, a.max_players or 0) > ROOM_MAX:
        ap.error(f"--min-players and --max-players can't be over {ROOM_MAX} (the game's lobby slots)")
    if a.fill_time < 0:
        ap.error("--fill-time can't be negative")
    try:
        build_policy = BuildGate(BuildAllowlist(a.build_allowlist)) if a.build_allowlist else None
    except (OSError, ValueError) as e:
        ap.error(str(e))
    blocklist = Blocklist(a.blocklist)
    admit = RangeAdmitFile(a.admit_file) if a.admit_file else None    # read only (v0.25, #452; ranges v0.29)
    cars, cars_note = None, "; car ids not checked (--no-cars)"
    if not a.no_cars:
        try:
            cars = load_cars(a.cars)
            cars_note = f"; car list: {len(cars)} cars"
        except FileNotFoundError:
            cars_note = f"; WARNING: car ids not checked, {a.cars} not found (copy tables/car-index.csv there)"
        except (OSError, ValueError) as e:
            ap.error(f"--cars {a.cars}: not a car list with a car_id column ({e})")
    max_players = a.max_players or a.min_players
    outdir = a.out if a.save else None
    if outdir:
        os.makedirs(outdir, exist_ok=True)
    socks = []
    for port, role in ((a.port, "master"), (a.game_port, "game")):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind((a.bind, port))
        socks.append((s, Server(role, a.record_only, a.game_host, a.game_port, a.min_players,
                                a.start_delay, Names(a.members, a.usernames, a.names, a.server_key),
                                a.countdown, a.relay_rate, a.idle, not a.no_id_check,
                                max_players, a.fill_time, a.max_conns, a.max_per_ip, build_policy,
                                blocklist, cars, None if a.no_leagues else Leagues(a.leagues),
                                Invites(a.invites), a.private_rooms if role == "game" else None,
                                a.private_ttl, admit,
                                a.selector_rooms if role == "game" else None,
                                a.status_file if role == "game" else None, not a.no_finish_release)))
    rooms = (f"{a.min_players}-{max_players}, waiting up to {a.fill_time:g} s for more"
             if a.fill_time > 0 and max_players > a.min_players else f"{a.min_players}")
    where = f"saving datagrams in {outdir}" if outdir else "not saving (--save to keep copies)"
    mode = ("recording only, nothing is answered" if a.record_only else
            f"master server :{a.port} (game server list -> {a.game_host or 'this PC'}:{a.game_port}), "
            f"game server :{a.game_port} (rooms of {rooms}, race start after {a.start_delay:g} s)")
    policy_note = (f"; build allowlist has {build_policy.count} allowed label(s); the game port "
                   "admits IPs the master allowed in the last 15 min") if build_policy else ""
    if admit is not None:
        policy_note += (f"; only IPs CC admitted in the last 15 min, or their /24 or /64 (v0.29) ({a.admit_file}"
                        + ("" if os.path.exists(a.admit_file) else ", missing: nobody until CC writes it") + ")")
    policy_note += f"; blocklist: {blocklist.describe()}" + cars_note
    policy_note += "; one room per event (--no-leagues)" if a.no_leagues else f"; rooms split by league ({a.leagues})"
    policy_note += f"; private rooms (invites, {a.private_ttl:g} s) listed in {a.private_rooms}"
    policy_note += f"; selector P2P rooms listed in {a.selector_rooms}"
    policy_note += f"; status every {STATUS_S:g} s in {a.status_file}"
    print(f"rr3_mp_server.py v{VERSION}. Listening on UDP {a.bind}, {mode}{policy_note}; {where} "
          "(Ctrl+C to stop)", flush=True)
    try:
        serve(socks, outdir)
    except KeyboardInterrupt:
        pass
    print("\nStopped." + (f" Datagrams saved in {outdir}" if outdir else ""))


if __name__ == "__main__":
    sys.exit(main())
