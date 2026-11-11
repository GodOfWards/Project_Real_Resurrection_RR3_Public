#!/usr/bin/env python3
"""Put key attestation (issue #204, phone side) into classes2.dex.

Part of Project Real Resurrection's work on Real Racing 3. Not affiliated
with, endorsed or supported by Electronic Arts.

Works on a baksmali'd classes2.dex (the folder `baksmali d -o DIR
classes2.dex` makes) that already has the APK signature label
(docs/apk-signature-label.md: GetInfo.GetDeviceMacAddress() returns
"sig:<sha256>"). It:

1. copies tools/attest-dex/PrrAttest.smali (compiled from
   tools/attest-dex/src/com/prr/PrrAttest.java) to DIR/com/prr/;
2. adds one guarded call at the top of GetDeviceMacAddress():

       :prr_attest_try_start
       invoke-static {}, Lcom/prr/PrrAttest;->start()V
       :prr_attest_try_end
       .catchall {:prr_attest_try_start .. :prr_attest_try_end} :prr_attest_catch
       :prr_attest_after
       ... the label's code, unchanged ...
       :prr_attest_catch
       goto :prr_attest_after

   start() only starts a background thread (once per game start) and
   returns; the try/catch keeps the sig: value even if the class were
   missing. The lib still gets "sig:<sha256>" at once;
3. (v2, issue #452) adds one guarded call in
   cloudcellapi/HttpThread.GetHttpConnection(), right after the line that
   adds the User-Agent (sget-object s_userAgent; addRequestProperty):

       :prr_headers_try_start
       invoke-static {p1}, Lcom/prr/PrrAttest;->addHeaders(Ljava/net/URLConnection;)V
       :prr_headers_try_end
       .catchall {:prr_headers_try_start .. :prr_headers_try_end} :prr_headers_catch
       :prr_headers_after
       ... the method's code, unchanged ...
       :prr_headers_catch
       goto :prr_headers_after

   addHeaders() adds X-PRR-Sig and X-PRR-Att (the token from CC v5.58)
   to every Cloudcell request: syncs and asset downloads.

--restore only finds the hooks in a folder this tool patched (before a
smali/baksmali round trip, which drops our comments and label names); on a
re-disassembled dex it removes the class and reports "incomplete". The
calls left behind are harmless (each sits in its own try/catch).

Then assemble the folder again (`smali a DIR -o classes2.dex`) and swap
the file in the APK as for the label (docs/key-attestation.md).

Versions (dex_contents() reports "attest-dex@vN"; named so on purpose:
rr3_patch_sites.py takes a tool with contents() for a lib patch tool, and
this one patches classes2.dex, not the lib. rr3_build.py patches can't see
it, so a build's builds.csv row names it by hand):
  v1  (issue #204): first version; server http://servers.devel60.net:62002.
  v2  (issue #452): the X-PRR-Sig / X-PRR-Att headers (hook 3); keeps CC
      v5.58's token in files/doc/prr_att.dat; logs no token.
  v3  (issue #248): the attestation thread no longer gives up: network
      errors and non-200 answers are tried again (30 s, doubling to every
      5 min) for as long as the game runs, the secret is waited for
      without a limit, and the token is renewed 1 h before it expires.
      CC's refusal still ends it until the next game start. Same hooks
      as v2; only the class changes.

Usage:
  rr3_attest_dex.py check DIR
  rr3_attest_dex.py apply DIR
  rr3_attest_dex.py apply DIR --version 2   (v2: gives up after 3 tries, for testing)
  rr3_attest_dex.py apply DIR --version 1   (v1: no headers, for testing)
  rr3_attest_dex.py apply DIR --restore     (back to the label alone)
"""
import argparse
import hashlib
import os
import re
import sys

VERSION = 3
HERE = os.path.dirname(os.path.abspath(__file__))
CLASS_SMALI = os.path.join(HERE, "attest-dex", "PrrAttest.smali")
CLASS_MD5 = "1ce32efb0a88a2e1b4548773de7038f7"      # PrrAttest.smali, version 3
CLASSES = {                                         # version -> (file, md5)
    1: (os.path.join(HERE, "attest-dex", "PrrAttest-v1.smali"), "2fb0f9686601b3c4ff6b16c7634e7235"),
    2: (os.path.join(HERE, "attest-dex", "PrrAttest-v2.smali"), "599802e07e658ac27410bcd5ab2bb020"),
    3: (CLASS_SMALI, CLASS_MD5),
}
GETINFO = os.path.join("com", "firemonkeys", "cloudcellapi", "util", "GetInfo.smali")
HTTPTHREAD = os.path.join("com", "firemonkeys", "cloudcellapi", "HttpThread.smali")
TARGET = os.path.join("com", "prr", "PrrAttest.smali")
METHOD_RE = re.compile(r"^\.method public static GetDeviceMacAddress\(\)Ljava/lang/String;\n.*?^\.end method\n",
                       re.M | re.S)

HOOK_START = """
    # Project Real Resurrection (issue #204): key attestation in a background thread
    :prr_attest_try_start
    invoke-static {}, Lcom/prr/PrrAttest;->start()V
    :prr_attest_try_end
    .catchall {:prr_attest_try_start .. :prr_attest_try_end} :prr_attest_catch

    :prr_attest_after
"""
HOOK_END = """
    :prr_attest_catch
    goto :prr_attest_after
"""
CONN_RE = re.compile(r"^\.method public GetHttpConnection\(Ljava/net/URL;\)Ljava/net/HttpURLConnection;\n.*?^\.end method\n",
                     re.M | re.S)
UA_RE = re.compile(r"^    sget-object (\w+), Lcom/firemonkeys/cloudcellapi/HttpRequest;->s_userAgent:Ljava/lang/String;\n\n?"
                   r"    invoke-virtual \{(\w+), \w+, \1\}, Ljava/net/URLConnection;->addRequestProperty"
                   r"\(Ljava/lang/String;Ljava/lang/String;\)V\n", re.M)
HEADERS_START = """
    # Project Real Resurrection (issue #452): X-PRR-Sig and X-PRR-Att on every request
    :prr_headers_try_start
    invoke-static {%s}, Lcom/prr/PrrAttest;->addHeaders(Ljava/net/URLConnection;)V
    :prr_headers_try_end
    .catchall {:prr_headers_try_start .. :prr_headers_try_end} :prr_headers_catch

    :prr_headers_after
"""
HEADERS_END = """
    :prr_headers_catch
    goto :prr_headers_after
"""


def md5(path):
    """md5 of the file with CRLF read as LF: baksmali on Windows writes CRLF,
    and the class is the same (seen 2026-11-05, Tom's PC)."""
    with open(path, "rb") as f:
        return hashlib.md5(f.read().replace(b"\r\n", b"\n")).hexdigest()


def method(text):
    m = METHOD_RE.findall(text)
    if len(m) != 1:
        raise SystemExit(f"GetDeviceMacAddress() found {len(m)} times in {GETINFO} (expected 1)")
    return m[0]


def conn_method(text):
    m = CONN_RE.findall(text)
    if len(m) != 1:
        raise SystemExit(f"GetHttpConnection() found {len(m)} times in {HTTPTHREAD} (expected 1)")
    return m[0]


def headers_hooked(d):
    """True if GetHttpConnection() has our addHeaders() call (v2)."""
    p = os.path.join(d, HTTPTHREAD)
    if not os.path.isfile(p):
        raise SystemExit(f"{p} not found: is {d} a baksmali'd classes2.dex?")
    with open(p, encoding="utf-8") as f:
        return "Lcom/prr/PrrAttest;->addHeaders(" in conn_method(f.read())


def set_headers(d, on):
    """Add (on) or remove the addHeaders() call in GetHttpConnection()."""
    p = os.path.join(d, HTTPTHREAD)
    with open(p, encoding="utf-8") as f:
        text = f.read()
    m = conn_method(text)
    hooked = "Lcom/prr/PrrAttest;->addHeaders(" in m
    if on == hooked:
        return
    if on:
        found = list(UA_RE.finditer(m))
        if len(found) != 1 or not m.endswith(".end method\n"):
            raise SystemExit(f"the User-Agent line was found {len(found)} times in GetHttpConnection(); not changed")
        u = found[0]
        new = (m[:u.end()] + HEADERS_START % u.group(2) + m[u.end():-len(".end method\n")].rstrip("\n")
               + "\n" + HEADERS_END + ".end method\n")
    else:
        reg = re.search(r"invoke-static \{(\w+)\}, Lcom/prr/PrrAttest;->addHeaders", m).group(1)
        new = m.replace(HEADERS_START % reg, "", 1).replace(HEADERS_END, "", 1)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text.replace(m, new, 1))


def state(d):
    """(label, hook, class, headers) found in DIR: label True if the method
    is the signature label; hook True if our start() call is in it; class
    the version of com/prr/PrrAttest.smali (None if missing, 0 if unknown);
    headers True if GetHttpConnection() calls addHeaders() (v2)."""
    p = os.path.join(d, GETINFO)
    if not os.path.isfile(p):
        raise SystemExit(f"{p} not found: is {d} a baksmali'd classes2.dex?")
    with open(p, encoding="utf-8") as f:
        m = method(f.read())
    label = '"sig:none"' in m and "MessageDigest" in m
    hook = "Lcom/prr/PrrAttest;->start()V" in m
    c = os.path.join(d, TARGET)
    cls = None
    if os.path.isfile(c):
        cls = next((v for v, (_f, h) in CLASSES.items() if md5(c) == h), 0)
    return label, hook, cls, headers_hooked(d)


def dex_contents(d):
    label, hook, cls, headers = state(d)
    parts = []
    if label:
        parts.append("sig-label")
    if hook and cls and headers == (cls >= 2):
        parts.append(f"attest-dex@v{cls}")
    elif hook or cls is not None or headers:
        parts.append("attest-dex(incomplete)")
    return parts


def check(d):
    label, hook, cls, headers = state(d)
    print(f"signature label: {'yes' if label else 'NO'}")
    print(f"start() call in GetDeviceMacAddress: {'yes' if hook else 'no'}")
    print(f"addHeaders() call in GetHttpConnection: {'yes' if headers else 'no'}")
    print("com/prr/PrrAttest.smali: " + ("missing" if cls is None else f"version {cls}" if cls
                                         else "present but not a known version"))
    print("contents: " + (", ".join(dex_contents(d)) or "-"))
    return 0 if label else 1


def apply(d, restore=False, version=VERSION):
    if version not in CLASSES:
        raise SystemExit(f"no version {version}; known: {sorted(CLASSES)}")
    src, want = CLASSES[version]
    if md5(src) != want:
        raise SystemExit(f"{src} is not version {version} (md5 {md5(src)}); "
                         "update CLASSES with a new version")
    label, hook, _cls, _headers = state(d)
    if not label:
        raise SystemExit("GetDeviceMacAddress() is not the signature label: apply "
                         "docs/details/apk-signature-label-details.md section 2 first")
    if not restore and version >= 2 and not _headers:     # refuse before writing anything
        with open(os.path.join(d, HTTPTHREAD), encoding="utf-8") as f:
            n = len(UA_RE.findall(conn_method(f.read())))
        if n != 1:
            raise SystemExit(f"the User-Agent line was found {n} times in GetHttpConnection(); not changed")
    p = os.path.join(d, GETINFO)
    with open(p, encoding="utf-8") as f:
        text = f.read()
    m = method(text)
    if restore:
        new = m.replace(HOOK_START, "", 1).replace(HOOK_END, "", 1) if hook else m
        c = os.path.join(d, TARGET)
        if os.path.exists(c):
            os.remove(c)
        set_headers(d, False)
    else:
        new = m
        if not hook:
            head = re.match(r"\.method[^\n]*\n\s*\.(?:registers|locals) \d+\n", m)
            if not head or not m.endswith(".end method\n"):
                raise SystemExit("unexpected method layout; not changed")
            body = m[head.end():-len(".end method\n")]
            new = head.group(0) + HOOK_START + body.rstrip("\n") + "\n" + HOOK_END + ".end method\n"
        os.makedirs(os.path.dirname(os.path.join(d, TARGET)), exist_ok=True)
        with open(src, "rb") as fs, open(os.path.join(d, TARGET), "wb") as dst:
            dst.write(fs.read())
        set_headers(d, version >= 2)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text.replace(m, new, 1))
    print(("restored: " if restore else "applied: ") + (", ".join(dex_contents(d)) or "-"))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="what DIR has")
    c.add_argument("dir")
    a = sub.add_parser("apply", help="add (or with --restore remove) the class and the call")
    a.add_argument("dir")
    a.add_argument("--restore", action="store_true")
    a.add_argument("--version", type=int, default=VERSION, help=f"write this version (default {VERSION})")
    args = ap.parse_args(argv)
    if args.cmd == "check":
        return check(args.dir)
    return apply(args.dir, args.restore, args.version)


if __name__ == "__main__":
    sys.exit(main())
