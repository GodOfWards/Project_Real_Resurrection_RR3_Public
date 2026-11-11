#!/usr/bin/env python3
"""Send the game's Cloudcell sync requests (leaderboards, ghosts, OMP match
records, ...) and, with part cdn, its asset downloads to servers of our own
instead of EA's dead hosts and, with part fallback, its Cloudcell asset
fallback too, in libRealRacing3.so (v14.0.1, arm64, develified
build). Test patch for docs/cloudcell-test-server.md. Parts (--parts,
comma-separated; default sync):

  sync  CC_Sync.php requests and (v2) GET /time go to --host / --port (below).
  cdn   asset downloads go to --cdn-host (below, issue #167).
  fallback  the Cloudcell asset fallback goes to --fallback-host (below).

On the installed build Cloudcell runs in its "Live" environment
(0037-connect.cloudcell.com) or, in one log, switched to "Sandbox"
(connect-sandbox.cloudcell.com); either way every `CC_Sync.php` POST goes
to https://...:443 and fails. This patch changes:

  host  GetDefaultDomain (EnvironmentManager.cpp), both environments seen
        on the phone:
        - Sandbox branch: the string at 0x49b152
          "connect-sandbox.cloudcell.com" becomes HOST and its length
          `mov w9, #29` at 0x1cf0b10 becomes len(HOST).
        - Live branch: the format "%04u-%s%s.cloudcell.com" at 0x40c8a1
          (only user 0x1cf0e60, printed with vsnprintf by 0x1cf0f1c) becomes
          HOST, a format without any %, so the game id / "connect" /
          "assets" arguments are ignored. Live's assets domain does not
          use this format (it is set at start-up from a literal), so it
          does not move (analysis/asset-download.md).
        HOST defaults to 127.0.0.1 (at most 23 characters).
  port  The two CC_Sync.php request builders (0x1d006b0 and 0x1d035e8) load
        the port from the constant 443 at 0x5ff3d4 (`ldr w4, [xN]`). They
        become `mov w4, #PORT` (default 8080). The request constructor
        0x1c754a0 sets "use https" only when the port is 443, so any other
        port gives a plain http:// URL.

  time  (sync v2, issue #197) Cloudcell's server time request, GET /time,
        is built by 0x1c762b8 (its only caller is cc::ServerTimeManager),
        which loads the port from the domain info:
        0x1c7631c `ldr w4, [x22, #0x18]` (443) becomes `mov w4, #PORT`, the
        same --port, so /time goes to http://HOST:PORT/time like the syncs.
        The game reads the reply header X-Request-Start (strtod, Unix time
        in seconds) as the server time; rr3_cc_server.py answers it since
        v5.14. With a real server time the OMP cards count down without the
        debug menu's Override Server Time.

Sync versions (`check` knows both, `patch` writes the latest):
  v2  host + port + time. Not tested in game.
  v1  host + port only: /time keeps https on 443 and fails (b20..b42).
      `--sync-version 1` writes it.
Other hosts (draper pop-ups, Nimble/Java) are not touched.

  cdn   The asset CDN domain "firemonkeys.akamaized.net" at 0x42dbec (only
        user 0x1cf0a10, GetDefaultDomain type 1) becomes CDN_HOST. The code
        copies a fixed 25 bytes and takes the string's size, 25, from the
        constant at 0x388420 (shared by 118 sites, and by the env 6 path
        that joins at 0x1cf0a14), so CDN_HOST must be exactly 25
        characters: a shorter one would leave NUL bytes inside the host.
        No port in it: the request builder 0x1c757c4 adds ":443" after
        the host, so "servers.devel60.net:00443" (b38, b39) gave
        "https://servers.devel60.net:00443:443//rr3/live/..." and every
        download failed before connecting (tested 2026-10-26,
        analysis/asset-download.md). Use a 25-character host name (b42,
        working: "rr3bigboobies.devel60.net", behind Cloudflare), or
        userinfo padding (b41, accepted): "rr3ad@servers.devel60.net"
        ("rr3 asset downloads") keeps the host and its certificate, and
        the URL becomes "https://rr3ad@HOST:443//...".
        The domain keeps port 443, so the request is https.
        --cdn-short (test only, b40) allows a shorter host, padded with
        NUL bytes to 25, to see in logcat what URL the game builds then.
        AssetManager copies the CDN host at start-up, while the game is
        still in Live (analysis/asset-download.md).

  fallback  When the CDN fails, the game POSTs to
        /assetman/assetManDownloadPackHash.php on Live's Cloudcell assets
        domain (type 2). Its host is the literal "0037-assets.cloudcell.com"
        at 0x39f58d (only user 0xcd2f2c, the Cloudcell init, when
        CLOUDCELL_FallbackAssetServerEnabled >= 1), copied like the CDN
        string: a fixed 25 bytes (16-byte loads at +0 and +9), the size 25
        from the constant at 0x388420, port 443, https. It becomes
        FALLBACK_HOST, with the same rules as CDN_HOST: exactly 25
        characters, no port. Only the host moves: the server must answer
        that POST (body: a zlib BinaryBlob of md5 values; reply format not
        known yet, analysis/asset-download.md section 6). No other
        cloudcell.com host is touched.

Android blocks plain http unless the APK allows cleartext traffic (log
2026-10-14: "Cleartext HTTP traffic to ... not permitted"), see
docs/details/cloudcell-test-server-details.md.

Usage:
  rr3_cc_local.py check LIB
  rr3_cc_local.py patch IN OUT [--parts sync,cdn] [--host 127.0.0.1] [--port 8080]
                               [--sync-version {1,2}] [--cdn-host HOST25 [--cdn-short]]
                               [--fallback-host HOST25] [--restore]
IN may be gzipped; OUT is written uncompressed (or gzipped if it ends in .gz).
"""
import argparse
import gzip
import re
import struct
import sys

HOST_AT = 0x49B152                 # .rodata VMA == file offset
HOST_DEVELIFIED = b"connect-sandbox.cloudcell.com"
FMT_AT = 0x40C8A1                  # .rodata
FMT_DEVELIFIED = b"%04u-%s%s.cloudcell.com"
HOST_MAX = len(FMT_DEVELIFIED)          # 23, neither string can grow
LEN_AT = 0x1CF0B10                 # mov w9, #len
PORT_SITES = {0x1D006B0: 0xB9400164,   # ldr w4, [x11]
              0x1D035E8: 0xB9400124}   # ldr w4, [x9]
TIME_AT = 0x1C7631C                # GET /time builder 0x1c762b8 (sync v2)
TIME_DEVELIFIED = 0xB9401AC4       # ldr w4, [x22, #0x18]
SYNC_LATEST = 2
CDN_AT = 0x42DBEC                  # .rodata, then its 0 at 0x42dc05
CDN_DEVELIFIED = b"firemonkeys.akamaized.net"
CDN_LEN = len(CDN_DEVELIFIED)           # 25, fixed by the copy code (see cdn)
FALLBACK_AT = 0x39F58D             # .rodata, then its 0 at 0x39f5a6
FALLBACK_DEVELIFIED = b"0037-assets.cloudcell.com"
assert len(FALLBACK_DEVELIFIED) == CDN_LEN   # same fixed 25-byte copy
HOST25 = rb"[A-Za-z0-9.:@-]+"
PARTS = {"sync": "CC_Sync.php requests to our server",
         "cdn": "asset downloads to our CDN host",
         "fallback": "the Cloudcell asset fallback to our host"}


def movz_w(reg, imm):
    assert 0 <= imm < 0x10000
    return 0x52800000 | (imm << 5) | reg


def load(path):
    data = open(path, "rb").read()
    return bytearray(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def word(d, a):
    return struct.unpack_from("<I", d, a)[0]


def state(d):
    host = bytes(d[HOST_AT:HOST_AT + len(HOST_DEVELIFIED) + 1]).split(b"\0")[0]
    fmt = bytes(d[FMT_AT:FMT_AT + len(FMT_DEVELIFIED) + 1]).split(b"\0")[0]
    ln = word(d, LEN_AT)
    ports = [word(d, a) for a in PORT_SITES]
    tm = word(d, TIME_AT)
    if (host == HOST_DEVELIFIED and fmt == FMT_DEVELIFIED and ln == movz_w(9, len(HOST_DEVELIFIED))
            and ports == list(PORT_SITES.values()) and tm == TIME_DEVELIFIED):
        return "develified (syncs go to https://0037-connect / connect-sandbox .cloudcell.com:443)"
    if fmt == FMT_DEVELIFIED and ln == movz_w(9, len(host)) and host != HOST_DEVELIFIED:
        old = True                     # b19: Sandbox only
    elif fmt == host and ln == movz_w(9, len(host)):
        old = False
    else:
        return None
    pv = set()
    for w in ports:
        if w & 0xFFE0001F != 0x52800004:
            return None
        pv.add((w >> 5) & 0xFFFF)
    if len(pv) != 1:
        return None
    port = pv.pop()
    if tm == TIME_DEVELIFIED:
        v, time = 1, "; /time not moved"
    elif tm == movz_w(4, port) and not old:
        v, time = 2, " and /time"
    else:
        return None
    scheme = "https" if port == 443 else "http"
    which = "Sandbox syncs only (b19 version)" if old else "Live and Sandbox syncs"
    return f"patched v{v} ({which} go to {scheme}://{host.decode()}:{port}/CC_Sync.php{time})"


def cdn_state(d, at=CDN_AT, develified=CDN_DEVELIFIED):
    """'' develified, the CDN host if patched, None unrecognised. A host shorter
    than 25 (--cdn-short) is returned with "+nulpad" after it."""
    b = bytes(d[at:at + CDN_LEN + 1])
    if b == develified + b"\0":
        return ""
    host = b[:CDN_LEN].rstrip(b"\0")
    if b[CDN_LEN] == 0 and b"\0" not in host and re.fullmatch(HOST25, host):
        return host.decode() + ("" if len(host) == CDN_LEN else "+nulpad")
    return None


def fallback_state(d):
    """'' develified, the fallback host if patched, None unrecognised."""
    h = cdn_state(d, FALLBACK_AT, FALLBACK_DEVELIFIED)
    return None if h and h.endswith("+nulpad") else h


def contents(d):
    """`patches` entry for rr3_build.py: '' develified, None unrecognised.
    e.g. cc-local=HOST:PORT live+sandbox+cdn=CDN_HOST (sync v1) or
    cc-local=sync@v2=HOST:PORT live+sandbox+cdn=CDN_HOST+fallback=HOST."""
    s, cdn, fb = state(d), cdn_state(d), fallback_state(d)
    if s is None or cdn is None or fb is None:
        return None
    on = []
    if not s.startswith("develified"):
        url = re.search(r"//([^/]+)/", s).group(1)
        on.append(("sync@v2=" if s.startswith("patched v2") else "") + url + (" sandbox-only" if "Sandbox syncs only" in s else " live+sandbox"))
    if cdn:
        on.append("cdn=" + cdn)
    if fb:
        on.append("fallback=" + fb)
    return "cc-local=" + "+".join(on) if on else ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("lib")
    p = sub.add_parser("patch")
    p.add_argument("inp")
    p.add_argument("out")
    p.add_argument("--parts", default="sync", help="comma-separated: " + ", ".join(PARTS) + " (default sync)")
    p.add_argument("--host", default="127.0.0.1", help="part sync: server host or IP (max 23 characters)")
    p.add_argument("--port", type=int, default=8080, help="part sync: server port (443 = https, anything else = http)")
    p.add_argument("--sync-version", type=int, choices=(1, 2), default=SYNC_LATEST,
                   help=f"part sync: 1 = CC_Sync.php only, 2 = also /time (default {SYNC_LATEST})")
    p.add_argument("--cdn-host", help=f"part cdn: asset host, exactly {CDN_LEN} characters, no port (user@host allowed)")
    p.add_argument("--cdn-short", action="store_true",
                   help="part cdn, test only: allow a host shorter than 25, padded with NUL bytes")
    p.add_argument("--fallback-host",
                   help=f"part fallback: Cloudcell asset fallback host, exactly {CDN_LEN} characters, no port")
    p.add_argument("--restore", action="store_true", help="put the develified bytes back (of the parts given)")
    a = ap.parse_args()

    d = load(a.lib if a.cmd == "check" else a.inp)
    s, cdn, fb = state(d), cdn_state(d), fallback_state(d)
    if s is None:
        sys.exit("unexpected bytes at the sync sites: not the v14.0.1 develified build?")
    if cdn is None:
        sys.exit("unexpected bytes at the cdn site: not the v14.0.1 develified build?")
    if fb is None:
        sys.exit("unexpected bytes at the fallback site: not the v14.0.1 develified build?")
    if a.cmd == "check":
        print(f"sync: {s}")
        print("cdn: " + (f"patched (asset downloads go to {cdn})" if cdn
                         else f"develified (asset downloads go to {CDN_DEVELIFIED.decode()})"))
        print("fallback: " + (f"patched (asset fallback goes to {fb})" if fb
                              else f"develified (asset fallback goes to {FALLBACK_DEVELIFIED.decode()})"))
        return

    parts = [x for x in a.parts.split(",") if x]
    for n in parts:
        if n not in PARTS:
            sys.exit(f"unknown part {n}: choose from {', '.join(PARTS)}")
    if "cdn" in parts:
        if a.restore:
            new = CDN_DEVELIFIED
        else:
            new = (a.cdn_host or "").encode()
            if a.cdn_short and 0 < len(new) < CDN_LEN:
                new = new.ljust(CDN_LEN, b"\0")
            if len(new) != CDN_LEN or not re.fullmatch(HOST25, new.rstrip(b"\0")):
                sys.exit(f"--cdn-host must be exactly {CDN_LEN} characters (letters, digits, '.', '-', ':', '@'), "
                         f"got {len(new)}: a shorter host would leave NUL bytes in the game's string")
        d[CDN_AT:CDN_AT + CDN_LEN] = new
    if "fallback" in parts:
        new = FALLBACK_DEVELIFIED if a.restore else (a.fallback_host or "").encode()
        if len(new) != CDN_LEN or not re.fullmatch(rb"[A-Za-z0-9.@-]+", new):
            sys.exit(f"--fallback-host must be exactly {CDN_LEN} characters (letters, digits, '.', '-', '@'; "
                     f"no port), got {len(new)}")
        d[FALLBACK_AT:FALLBACK_AT + CDN_LEN] = new
    if "sync" in parts:
        write_sync(d, a)
    out = gzip.compress(bytes(d)) if a.out.endswith(".gz") else bytes(d)
    open(a.out, "wb").write(out)
    print(f"{a.out}: sync {state(d)}; cdn {cdn_state(d) or 'develified'}; "
          f"fallback {fallback_state(d) or 'develified'}")


def write_sync(d, a):
    if a.restore:
        host, ports, tm = HOST_DEVELIFIED, list(PORT_SITES.values()), TIME_DEVELIFIED
    else:
        host = a.host.encode()
        if not 0 < len(host) <= HOST_MAX or b"\0" in host:
            sys.exit(f"--host must be 1-{HOST_MAX} characters")
        if not 0 < a.port < 0x10000:
            sys.exit("--port must be 1-65535")
        ports = [movz_w(4, a.port)] * len(PORT_SITES)
        tm = movz_w(4, a.port) if a.sync_version >= 2 else TIME_DEVELIFIED
    if a.restore:
        d[FMT_AT:FMT_AT + len(FMT_DEVELIFIED) + 1] = FMT_DEVELIFIED + b"\0"
    else:
        d[FMT_AT:FMT_AT + len(FMT_DEVELIFIED) + 1] = host + b"\0" * (len(FMT_DEVELIFIED) + 1 - len(host))
    d[HOST_AT:HOST_AT + len(HOST_DEVELIFIED) + 1] = host + b"\0" * (len(HOST_DEVELIFIED) + 1 - len(host))
    struct.pack_into("<I", d, LEN_AT, movz_w(9, len(host)))
    for addr, w in zip(PORT_SITES, ports):
        struct.pack_into("<I", d, addr, w)
    struct.pack_into("<I", d, TIME_AT, tm)


if __name__ == "__main__":
    main()
