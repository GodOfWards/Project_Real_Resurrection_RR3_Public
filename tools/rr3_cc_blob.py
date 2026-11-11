#!/usr/bin/env python3
"""Decode the Cloudcell sync requests Real Racing 3 sends to CC_Sync.php
(the bodies saved by rr3_cc_server.py) and build the replies the server
sends (wrap(), reply(), leaderboard_rows()). Format:
docs/details/cloudcell-sync-format.md.

Body = BinaryBlob wrapper (BinaryBlob.cpp, wrap 0x1cbd66c / unwrap 0x1cbd8f0):
  u32 checksum (0x1cb9734) over everything after these 8 bytes
  u32 mode     0 = plain, 1 = zlib (u32 plain size + zlib data),
               2 = XOR (u8 seed k, then each byte XOR k, k += 3)
The game sends mode 2 around mode 1. Inside: a header (app, device, session)
and a list of subsyncs, each `u32 type, u32 type2, u32 0, u32 size, payload`.

Usage:
  rr3_cc_blob.py show FILE... [--hex]   list the subsyncs of each request
  rr3_cc_blob.py plain FILE OUT         write the decoded request to OUT
  rr3_cc_blob.py history FILE...        list the Time Trial results in the
                                        race history (subsync 10451)

The header holds device identifiers (Android id, a UUID, model); `show`
does not print them, but don't share `plain` output publicly.
"""
import re
import struct
import sys
import zlib

# type -> name, from the subsync constructors (docs/details/multiplayer-details.md 2.3)
NAMES = {
    10452: "PlayerRankSync", 10469: "DownloadRandomProgressSaveGameSync",
    10477: "LeaderBoardSync", 10484: "LeaderBoardGroupSync",
    10486: "LeaderBoardFriendsSync", 10514: "LeaderBoardEntrySync",
    10516: "LeaderBoardCCMemberIdSync",
    10532: "OnlineMultiplayerFinishedMatch/DisconnectionSync",
    10545: "UploadVehiclesSync", 10548: "OnlineMultiplayerMemberStatusSync",
    10607: "GetPlayerGarageSync", 10626: "OnlineMultiplayerStartMatchSync",
    10630: "GetCustomisationInfoSync", 10768: "PingTestGetServersSync",
    10788: "LeaderBoardValidateSync",
    10451: "race history (last races, see race_history)",
    # ghosts (issue #94, analysis/leaderboard-ghosts.md); not constructor names
    10476: "ghost download", 10694: "ghost link",
    10695: "ghost upload slot", 10696: "ghost upload failed",
}
HEADER_END = 310          # offset of the auth block's final -1 in every capture (2026-10-14)


def s8(x):
    return x - 256 if x > 127 else x


def checksum(b):
    """0x1cb9734: per 4 signed bytes a*b*c/d (d skipped when 0), summed."""
    n, t = len(b), 0
    for i in range(0, n, 4):
        v = s8(b[i])
        if i + 1 < n:
            v *= s8(b[i + 1])
        if i + 2 < n:
            v *= s8(b[i + 2])
        if i + 3 < n and b[i + 3]:
            d = s8(b[i + 3])
            q = abs(v) // abs(d)
            v = q if (v < 0) == (d < 0) else -q
        t = (t + v) & 0xFFFFFFFF
    return t


MAX_PLAIN = 4 << 20       # largest unpacked body accepted (issue #143; 155 queued results are 10 KB)
BUILD_REPORT_RE = re.compile(
    rb"RealRacing3/[0-9]+(?:\.[0-9]+)+ \[(PRR [bi][0-9]{2,}-(?:alpha|beta|stable|support))\]"   # i: iOS (#299)
)
BUILD_REPORT_PREFIX = 256


def unwrap(d, max_plain=MAX_PLAIN):
    """Undo the wrapper layers; returns (plain bytes, [modes]). Only what
    the game sends is accepted (issue #143): at most one XOR layer, and only
    as the outer one, then zlib or plain; zlib must unpack to its declared
    size, at most max_plain bytes."""
    modes = []
    while True:
        if len(d) < 8:
            raise ValueError("too short")
        chk, mode = struct.unpack_from("<II", d)
        if mode == 2 and modes:
            raise ValueError("nested XOR layer")
        if chk != checksum(d[8:]):
            raise ValueError(f"bad checksum (mode {mode})")
        modes.append(mode)
        if mode == 2:
            if len(d) < 9:
                raise ValueError("too short")
            k, out = d[8], bytearray()
            for b in d[9:]:
                out.append(b ^ k)
                k = (k + 3) & 0xFF
            d = bytes(out)
        elif mode == 1:
            if len(d) < 12:
                raise ValueError("too short")
            n = struct.unpack_from("<I", d, 8)[0]
            if n > max_plain:
                raise ValueError(f"zlib size {n} over the limit {max_plain}")
            z = zlib.decompressobj()
            d = z.decompress(d[12:], n + 1)       # one byte more shows a longer stream
            if len(d) != n or not z.eof:
                raise ValueError("zlib size mismatch")
            return d, modes
        elif mode == 0:
            return d[8:], modes
        else:
            raise ValueError(f"unknown mode {mode}")


def wrap(plain, mode, seed=0x5A):
    """Build a blob the way the game does (for replies from a test server)."""
    if mode == 0:
        body = plain
    elif mode == 1:
        body = struct.pack("<I", len(plain)) + zlib.compress(plain, 9)
    elif mode == 2:
        k, out = seed & 0xFF, bytearray([seed & 0xFF])
        for b in plain:
            out.append(b ^ k)
            k = (k + 3) & 0xFF
        body = bytes(out)
    else:
        raise ValueError(mode)
    return struct.pack("<II", checksum(body), mode) + body


USERNAME_PREFIX = "rrname:"
# Same rules as rr3_username.py v3 (name_ok); v1/v2 names are a subset.
USERNAME_RE = re.compile(r"[A-Za-z0-9_.!?~+*#-]{3,16}")
# APK signature label (issue #143, docs/apk-signature-label.md): an APK with
# the smali change sends "sig:" + the SHA-256 of its signing certificate (64
# lowercase hex) in place of the Wi-Fi MAC, or "sig:none" when it can't.
SIG_PREFIX = "sig:"
SIG_RE = re.compile(r"[0-9a-f]{64}")
# Player secret (issue #218, #163 Decided 1.2): a lib with the secret patch
# sends "rrsecret:" + 64 lowercase hex (32 random bytes made on the phone).
SECRET_PREFIX = "rrsecret:"
SECRET_RE = re.compile(r"[0-9a-f]{64}")


UUID_RE = re.compile(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}")


def id_shape(t):
    """The shape of a header string, never its value (issue #299): to see
    which ids a phone sends (an iPhone has no Android id) without logging
    them. uuid (uuid0 if all zeros), 16hex, hexN, digitsN or textN."""
    if UUID_RE.fullmatch(t):
        return "uuid0" if set(t) <= set("0-") else "uuid"
    if re.fullmatch(r"[0-9a-f]{16}", t):
        return "16hex"
    if re.fullmatch(r"[0-9]+", t):
        return f"digits{len(t)}"
    if re.fullmatch(r"[0-9a-fA-F]+", t):
        return f"hex{len(t)}"
    return f"text{len(t)}"


def typed_at(d, i):
    """Whether a typed header entry (u32 type below 16, u32 length 1..127,
    printable string) starts at i. The entry count before the first entry
    looks like one too (count 6, then type 1 read as a length): header()
    skips a word when the next word also starts an entry."""
    if i + 8 > len(d):
        return False
    t, n = struct.unpack_from("<2I", d, i)
    s = d[i + 8:i + 8 + n]
    return 0 < t < 16 and 0 < n < 128 and len(s) == n and all(32 <= c < 127 for c in s)


def header(d):
    """Read the request header: u32 values and u32-length strings, up to the
    u32 -1 that ends it (offset 310 in every capture of Tom's phone; it moves
    when a string such as the Synergy id is shorter or empty). Returns
    dict(android_id, synergy_id, username, sig, end): the 16-hex-digit
    Android id, the all-digit Synergy id ("" if none), the leaderboard
    username a lib patched with rr3_username.py adds as "rrname:<name>" (""
    if none or not 3..16 characters of A-Z a-z 0-9 _ - . ! ? ~ + * #), the
    signing-certificate digest an APK with the signature label sends as
    "sig:<64 hex>" ("" if no "sig:" string, "none" for "sig:" with anything
    else), the player secret a lib with the secret patch sends as
    "rrsecret:<64 hex>" ("" if none or not 64 lowercase hex digits) and the
    offset of the -1. shapes: id_shape() of every other string, in order
    (issue #299; the values are not kept); a typed entry's shows as
    "TYPE:shape".

    Typed entries (CC v5.46, issue #299): the header holds a count and
    entries of u32 type + string (an iPhone: 6 entries, type 1 = its
    identifierForVendor, type 3 = advertising id; ios-patch-details.md
    section 14). A type below 16 followed by a printable string is read as
    one entry (before v5.46 a type 1 followed by a 36-character string was
    read as the 1-byte string "$" and the id was lost). idfv: the type-1
    value when it is a UUID that isn't all zeros, in upper case ("" if
    none). A real string can't be mistaken for an entry: its first four
    bytes, read as a length, are far above 127. A word is not read as a
    type when the next word starts an entry itself (the entry count, see
    typed_at())."""
    info = dict(android_id="", synergy_id="", username="", sig="", secret="", idfv="",
                end=HEADER_END, shapes=[])
    i = 0
    while i + 4 <= min(len(d), 1024):
        v = struct.unpack_from("<I", d, i)[0]
        if v == 0xFFFFFFFF:
            info["end"] = i
            break
        kind = None
        if 0 < v < 16 and typed_at(d, i) and not typed_at(d, i + 4):
            n = struct.unpack_from("<I", d, i + 4)[0]
            s = d[i + 8:i + 8 + n]
            kind, step = v, 8 + n
        if kind is None:
            s = d[i + 4:i + 4 + v]
            step = 4 + v
            ok = 0 < v < 128 and len(s) == v and all(32 <= c < 127 for c in s)
        else:
            ok = True
        if ok:
            t = s.decode()
            if kind == 1 and not info["idfv"] and UUID_RE.fullmatch(t) and set(t) - set("0-"):
                info["idfv"] = t.upper()
            elif t.startswith(USERNAME_PREFIX):
                name = t[len(USERNAME_PREFIX):]
                info["username"] = name if USERNAME_RE.fullmatch(name) else ""
            elif t.startswith(SIG_PREFIX):
                digest = t[len(SIG_PREFIX):]
                info["sig"] = digest if SIG_RE.fullmatch(digest) else "none"
            elif t.startswith(SECRET_PREFIX):
                secret = t[len(SECRET_PREFIX):]
                info["secret"] = secret if SECRET_RE.fullmatch(secret) else ""
            elif not info["android_id"] and re.fullmatch(r"[0-9a-f]{16}", t):
                info["android_id"] = t
            elif not info["synergy_id"] and re.fullmatch(r"[0-9]{8,20}", t):
                info["synergy_id"] = t
            else:
                info["shapes"].append((f"{kind}:" if kind is not None else "") + id_shape(t))
            i += step
        else:
            i += 4
    return info


def subsyncs(d, i=None):
    """Header ends with u32 -1 (see header()); subsyncs follow."""
    if i is None:
        i = header(d)["end"]
    if struct.unpack_from("<i", d, i)[0] != -1:
        raise ValueError("header end marker not found")
    i += 4
    out = []
    while i + 16 <= len(d):
        t, t2, z, n = struct.unpack_from("<IIII", d, i)
        if i + 16 + n > len(d):
            raise ValueError(f"subsync at {i} runs past the end")
        out.append((t, t2, z, d[i + 16:i + 16 + n]))
        i += 16 + n
    return out


def build_tag(d, subs=None):
    """Read the PRR build tag from type-68's compressed profile report.

    Returns the exact ``PRR bNN-channel`` (or iOS ``PRR iNN-channel``) label, or None if the report is
    absent, malformed, untagged, or contains conflicting labels. Type 68's
    Captures have opaque framing before the zlib stream, observed at offset
    4 or offset 12 (including b47's extra 8-byte header). The first u32 is
    not a reliable expanded-size field; only the first 256 output bytes are
    inflated at each candidate offset to find the build string.
    """
    found = set()
    for t, _t2, _z, payload in (subsyncs(d) if subs is None else subs):
        if t != 68:
            continue
        if len(payload) < 6:
            return None
        reports = []
        for compressed_at in (4, 12):
            try:
                z = zlib.decompressobj()
                reports.append(z.decompress(payload[compressed_at:], BUILD_REPORT_PREFIX))
            except zlib.error:
                continue
        if not reports:
            return None
        for report in reports:
            found.update(m.group(1).decode("ascii") for m in BUILD_REPORT_RE.finditer(report))
    return next(iter(found)) if len(found) == 1 else None


def report_head(d, subs=None, n=100):
    """The printable start of type-68's unpacked report (issue #299: where
    does an iPhone put its build line?): the first n characters, anything
    outside printable ASCII shown as '.', for each candidate offset that
    inflates; '' if there is no 68 or nothing inflates."""
    out = []
    for t, _t2, _z, payload in (subsyncs(d) if subs is None else subs):
        if t != 68 or len(payload) < 6:
            continue
        for compressed_at in (4, 12):
            try:
                r = zlib.decompressobj().decompress(payload[compressed_at:], BUILD_REPORT_PREFIX)
            except zlib.error:
                continue
            if r:
                out.append("".join(chr(c) if 32 <= c < 127 else "." for c in r[:n]))
        break
    return " | ".join(out)


def u32(*v):
    return b"".join(struct.pack("<i" if x < 0 else "<I", x) for x in v)


def string(t):
    b = t.encode() if isinstance(t, str) else t
    return u32(len(b)) + b


def leaderboard_rows(rows, player_row=0, total=None):
    """Reply payload for LeaderBoardSync (10477), read by 0xce06a8.

    Header A, B, C, N. A = the player's row (highlighted, repeated at the
    bottom). B = the leader's time in ms: the gap line shows i88 - B (code
    at 0xce35e4; 2026-10-14 screens showed time minus 5 with B=5 and minus 1
    with B=1). C = number of players (stored with a minimum of 1 next to
    the gap, likely for "TOP x%"; not confirmed).
    Rows (2026-10-14): s1 name, s5 tag, i8c car, time = PR, i84 rank
    counted from 0 (shown +1), i88 lap time in ms.
    """
    best = min((r["i88"] for r in rows), default=0)
    out = struct.pack("<i", player_row) + u32(best, total or len(rows), len(rows))
    for i, r in enumerate(rows):
        out += (string(r["s1"]) + u32(r["i18"]) + string(r["s2"]) + string(r["s3"])
                + u32(0)                              # skipped block: size 0
                + string(r["s4"]) + string(r["s5"]) + u32(r["i8c"])
                + struct.pack("<f", r["time"]) + string(r["s6"])
                + u32(r["i84"], r["i88"]) + u32(0)    # list of K ints: K = 0
                + u32(r["i80"]))
    return out


# 10451 payload: u32 count, then one 68-byte record per recent race
# (155 in Tom's capture of 2026-10-14). Fields named here were matched
# against known races; the rest are listed as f3..f10 (meaning unknown).
RACE_RECORD = struct.Struct("<11if5f")
MODE_TIME_TRIAL = 13


def race_history(payload):
    """Decode a 10451 payload into a list of dicts, oldest first."""
    n = struct.unpack_from("<I", payload)[0]
    if 4 + n * RACE_RECORD.size != len(payload):
        raise ValueError(f"10451: {n} records do not fill {len(payload)} bytes")
    out = []
    for i in range(n):
        r = RACE_RECORD.unpack_from(payload, 4 + i * RACE_RECORD.size)
        out.append(dict(build=r[0],          # 7469 now, 5675 for old races
                        event=r[1],          # event id (analysis/event-index)
                        mode=r[2],           # 13 = Time Trial
                        f3=r[3], f4=r[4], f5=r[5],
                        time_ms=r[6],        # result; lap time in ms for Time Trial
                        f7=r[7], f8=r[8],
                        car=r[9],            # car id (tables/car-index.csv)
                        f10=r[10],
                        pr=r[11],            # car PR (0 in old records)
                        stats=r[12:]))       # 0, then the car's 4 stat values
    return out


def leaderboard_request(payload):
    """10477 payload: u32 0, u32 1, u32 event id, u32 a, u32 b, 0, 0
    (a, b = 1, 1 or 21, 0; meaning not traced). Returns the event id."""
    return struct.unpack_from("<I", payload, 8)[0]


def reply(request_plain, answers, server_time, member_id=1):
    """Plain reply for one request: answers maps subsync type -> payload.

    Layout (0x1d03c7c): u32 status (non-zero), u32 value for
    cloudcell+0x4a0 vfunc 0xa0 (meaning not traced; server time assumed),
    auth block (LegacyManager reader 0x1cfb784: member id, developer flag,
    device id, value for cloudcell+0x488 vfunc 0xe0, flag), then for every
    subsync of the request, in order: u32 size + payload. A list value
    gives one payload per subsync of that type, in order (a request can
    hold 30+ ghost uploads, each needing its own key).
    """
    # member id 1 = the id the game logs at start ("CC: Member Id: 1");
    # 0 made it log "Member changed" (2026-10-14).
    out = u32(1, server_time) + u32(member_id, 0, 0, 0, 0)
    for t, _t2, _z, _p in subsyncs(request_plain):
        pl = answers.get(t, b"")
        if isinstance(pl, list):
            pl = pl.pop(0) if pl else b""
        out += u32(len(pl)) + pl
    return out


def main():
    a = sys.argv[1:]
    if len(a) >= 2 and a[0] == "show":
        hexdump = "--hex" in a
        for f in [x for x in a[1:] if x != "--hex"]:
            plain, modes = unwrap(open(f, "rb").read())
            print(f"{f}: modes {modes}, {len(plain)} bytes")
            for t, t2, z, p in subsyncs(plain):
                print(f"  {t:5d}/{t2:<5d} {NAMES.get(t, '?'):<36} {len(p):6d} bytes"
                      + (f"  {p[:64].hex(' ')}" if hexdump and p else ""))
    elif len(a) == 3 and a[0] == "plain":
        plain, _ = unwrap(open(a[1], "rb").read())
        open(a[2], "wb").write(plain)
        print(f"{a[2]}: {len(plain)} bytes")
    elif len(a) >= 2 and a[0] == "history":
        for f in a[1:]:
            plain, _ = unwrap(open(f, "rb").read())
            for t, _t2, _z, p in subsyncs(plain):
                if t != 10451:
                    continue
                for r in race_history(p):
                    if r["mode"] == MODE_TIME_TRIAL:
                        ms = r["time_ms"]
                        print(f"{f}: event {r['event']:6d}  car {r['car']:4d}  "
                              f"PR {r['pr']:5.1f}  {ms // 60000:02d}:{ms // 1000 % 60:02d}.{ms % 1000:03d}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
