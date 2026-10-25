#!/usr/bin/env python3
"""Let Real Racing 3 send plain http (cleartext) requests, for the local
Cloudcell test server (docs/cloudcell-test-server.md).

develified.apk (v14.0.1) blocks cleartext traffic: AndroidManifest.xml has
android:usesCleartextTraffic="false" and
android:networkSecurityConfig="@7F15000A", which points to one of the two
compiled XML files res/xml/network_security_config.xml and
res/xml/network_security_config_ad_tech.xml. On the phone this gives
"Cleartext HTTP traffic to 127.0.0.1 not permitted" (log 2026-10-14).

The network security config overrides the manifest attribute, so this tool
does not touch the manifest. It writes a replacement for BOTH files (we don't
know which one 0x7F15000A is without resources.arsc) that allows cleartext
to every host and keeps the normal system certificates for https:

  <network-security-config>
    <base-config cleartextTrafficPermitted="true">
      <trust-anchors><certificates src="system"/></trust-anchors>
    </base-config>
  </network-security-config>

The files are Android binary XML (AXML), written by this script; no Android
build tools are needed. Replace them in the APK with `zip` before zipalign
and apksigner (docs/commands.md).

Usage:
  rr3_cleartext.py show APK|FILE   print the network security config(s) as text
  rr3_cleartext.py make DIR        write DIR/res/xml/network_security_config*.xml
"""
import os
import struct
import sys
import zipfile

FILES = ["res/xml/network_security_config.xml",
         "res/xml/network_security_config_ad_tech.xml"]

T_STRING, T_BOOL = 0x03, 0x12


# ---------- writer ----------

def string_pool(strings):
    data = b""
    offs = []
    for s in strings:
        b = s.encode()
        assert len(s) < 128 and len(b) < 128
        offs.append(len(data))
        data += bytes([len(s), len(b)]) + b + b"\0"
    data += b"\0" * (-len(data) % 4)
    hdr = 28
    start = hdr + 4 * len(strings)
    body = b"".join(struct.pack("<I", o) for o in offs) + data
    return struct.pack("<HHIIIIII", 1, hdr, hdr + len(body), len(strings), 0,
                       0x100, start, 0) + body


def build(tree):
    """tree = (name, [(attr, type, value)], [children])"""
    strings = []

    def idx(s):
        if s not in strings:
            strings.append(s)
        return strings.index(s)

    chunks = []

    def walk(node, line):
        name, attrs, kids = node
        a = b""
        for an, t, v in attrs:
            if t == T_STRING:
                raw = data = idx(v)
            else:
                raw, data = 0xFFFFFFFF, v
            a += struct.pack("<iIIHBBI", -1, idx(an), raw, 8, 0, t, data)
        ext = struct.pack("<iIHHHHHH", -1, idx(name), 20, 20, len(attrs), 0, 0, 0) + a
        chunks.append(struct.pack("<HHIIi", 0x0102, 16, 16 + len(ext), line, -1) + ext)
        line += 1
        for k in kids:
            line = walk(k, line)
        chunks.append(struct.pack("<HHIIiiI", 0x0103, 16, 24, line, -1, -1, idx(name)))
        return line + 1

    walk(tree, 1)
    body = string_pool(strings) + b"".join(chunks)
    return struct.pack("<HHI", 3, 8, 8 + len(body)) + body


CONFIG = ("network-security-config", [], [
    ("base-config", [("cleartextTrafficPermitted", T_BOOL, 0xFFFFFFFF)], [
        ("trust-anchors", [], [
            ("certificates", [("src", T_STRING, "system")], []),
        ]),
    ]),
])


# ---------- reader ----------

def read_pool(d, o):
    _, hs, _, n, _, flags, start, _ = struct.unpack_from("<HHIIIIII", d, o)
    utf8 = flags & 0x100
    out = []
    for i in range(n):
        p = o + start + struct.unpack_from("<I", d, o + hs + 4 * i)[0]
        if utf8:
            p += 2 if d[p] & 0x80 else 1
            ln = d[p]
            if ln & 0x80:
                ln = ((ln & 0x7F) << 8) | d[p + 1]
                p += 1
            out.append(d[p + 1:p + 1 + ln].decode("utf-8", "replace"))
        else:
            ln = struct.unpack_from("<H", d, p)[0]
            out.append(d[p + 2:p + 2 + 2 * ln].decode("utf-16-le", "replace"))
    return out


def dump(d):
    if struct.unpack_from("<H", d, 0)[0] != 3:
        return "(not binary XML)"
    o, pool, depth, lines = 8, [], 0, []
    s = lambda i: pool[i] if 0 <= i < len(pool) else ""
    while o < len(d):
        t, hs, size = struct.unpack_from("<HHI", d, o)
        if t == 1:
            pool = read_pool(d, o)
        elif t == 0x0102:
            name, ast, asz, cnt = struct.unpack_from("<iHHH", d, o + 20)
            attrs = []
            for i in range(cnt):
                p = o + 16 + ast + i * asz
                _, an, raw, _, _, vt, vd = struct.unpack_from("<iiiHBBI", d, p)
                if vt == T_STRING:
                    v = s(vd)
                elif vt == T_BOOL:
                    v = "true" if vd else "false"
                elif vt == 0x01:
                    v = f"@{vd:08X}"
                else:
                    v = f"0x{vd:x} (type {vt:#x})"
                attrs.append(f' {s(an)}="{v}"')
            lines.append("  " * depth + f"<{s(name)}{''.join(attrs)}>")
            depth += 1
        elif t == 0x0103:
            depth -= 1
            lines.append("  " * depth + f"</{s(struct.unpack_from('<i', d, o + 20)[0])}>")
        elif t == 0x0104:
            lines.append("  " * depth + s(struct.unpack_from("<i", d, o + 16)[0]).strip())
        o += size
    return "\n".join(lines)


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("show", "make"):
        sys.exit(__doc__)
    cmd, path = sys.argv[1:]
    if cmd == "make":
        blob = build(CONFIG)
        for f in FILES:
            out = os.path.join(path, f)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            open(out, "wb").write(blob)
            print(f"wrote {out} ({len(blob)} bytes): cleartext allowed")
        return
    if zipfile.is_zipfile(path):
        z = zipfile.ZipFile(path)
        for f in FILES:
            print(f"== {f}")
            print(dump(z.read(f)) if f in z.namelist() else "(missing)")
    else:
        print(dump(open(path, "rb").read()))


if __name__ == "__main__":
    main()
