#!/usr/bin/env python3
"""Android key attestation for PRR servers (issue #204).

Part of Project Real Resurrection's work on Real Racing 3. Not affiliated
with, endorsed or supported by Electronic Arts.

The phone (our classes2.dex, not written yet) makes a key in its secure
hardware with an attestation challenge from our server and sends the
certificate chain. This module checks it:

1. the nonce was issued by us, is recent and unused;
2. the chain verifies, certificate by certificate, up to one of Google's
   attestation roots (ROOTS_PEM), and no certificate in it is on Google's
   revocation list (RevocationList);
3. the challenge is SHA-256(nonce || the player's secret), the secret the
   lib sends as ``rrsecret:`` (docs/prr-secret.md), so the proof belongs to
   that player;
4. the key lives in a TEE or StrongBox, not software;
5. the attested app is ``com.ea.games.r3_row`` signed by a trusted key
   (data/trusted-sigs.txt, the same named keys as the APK label);
6. the root of trust (bootloader locked, verified boot) is recorded, not
   judged.

A passing player counts as attested for TTL_S (24 h, decided in #204).
Policy: log only. Needs the ``cryptography`` package (a venv on the box,
#204); without it AVAILABLE is False and the server runs without
attestation. Everything else here is the standard library.

v1.0 (issue #204): first version.
v1.1 (issue #452): attestation tokens for other servers. make_token()
signs {"m", "k", "b", "l", "s", "exp"} with a CC-only key (base64 in a
0600 file, load_key_file()); read_token() checks one. Standard library
only, so another server (devel's asset server) can import or copy it.
v1.2 (issue #452): an expired CA certificate in the chain no longer fails
the proof (a Galaxy A40 was refused with "certificate 3 expired"); only a
not-before in the future does ("chain: certificate i not yet valid").
v1.3 (issue #452): lenient parse. Every certificate is read by our own DER
reader (Cert); the signature is checked over its signed tbsCertificate
bytes with the issuer's key, so a certificate the cryptography package
refuses (78 "chain: bad certificate" refusals on release night) can still
pass. Such a certificate is logged ("attest: lenient parse: certificate i:
<parser error>"); one our reader can't read either fails as
"chain: bad certificate i (<parser error>)".
"""
import base64
import calendar
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import urllib.request
import warnings

VERSION = "1.3"

try:
    from cryptography import x509
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
    AVAILABLE, WHY_NOT = True, ""
except ImportError as e:            # the server runs on without attestation
    x509 = InvalidSignature = serialization = hashes = ec = padding = rsa = None
    AVAILABLE, WHY_NOT = False, f"cryptography not installed ({e})"

PACKAGE = "com.ea.games.r3_row"
KEY_DESCRIPTION_OID = "1.3.6.1.4.1.11129.2.1.17"
STATUS_URL = "https://android.googleapis.com/attestation/status"
TTL_S = 24 * 3600               # an attestation counts this long (#204 decision 3)
NONCE_TTL_S = 300               # a challenge must come back within 5 min
NONCE_MAX = 10000               # challenges kept at most (oldest dropped)
CHAIN_MAX = 10                  # certificates in a chain at most
CERT_MAX = 16 * 1024            # bytes per certificate at most
SKEW_S = 24 * 3600              # clock leeway for a certificate's not-before
STATUS_REFRESH_S = 24 * 3600    # revocation list refreshed this often
STATUS_RETRY_S = 3600           # after a failed fetch

SECURITY_LEVELS = {0: "software", 1: "tee", 2: "strongbox"}
BOOT_STATES = {0: "verified", 1: "self-signed", 2: "unverified", 3: "failed"}

# Google's hardware attestation roots, from the official list
# https://android.googleapis.com/attestation/root (fetched 2026-11-05, md5
# of the JSON 23eafc5949228f26f099f93110acb7db): the RSA root (subject
# serialNumber f92009e853b6b045; older phones, e.g. Tom's A32) and the
# ECDSA P-384 "Key Attestation CA1" (2025; newer phones, e.g. the A15).
# A chain is accepted when it ends at a certificate with one of these
# public keys, or one directly issued by them. Re-check the official list
# when Google announces a new root.
ROOTS_PEM = """\
-----BEGIN CERTIFICATE-----
MIIFHDCCAwSgAwIBAgIJAPHBcqaZ6vUdMA0GCSqGSIb3DQEBCwUAMBsxGTAXBgNV
BAUTEGY5MjAwOWU4NTNiNmIwNDUwHhcNMjIwMzIwMTgwNzQ4WhcNNDIwMzE1MTgw
NzQ4WjAbMRkwFwYDVQQFExBmOTIwMDllODUzYjZiMDQ1MIICIjANBgkqhkiG9w0B
AQEFAAOCAg8AMIICCgKCAgEAr7bHgiuxpwHsK7Qui8xUFmOr75gvMsd/dTEDDJdS
Sxtf6An7xyqpRR90PL2abxM1dEqlXnf2tqw1Ne4Xwl5jlRfdnJLmN0pTy/4lj4/7
tv0Sk3iiKkypnEUtR6WfMgH0QZfKHM1+di+y9TFRtv6y//0rb+T+W8a9nsNL/ggj
nar86461qO0rOs2cXjp3kOG1FEJ5MVmFmBGtnrKpa73XpXyTqRxB/M0n1n/W9nGq
C4FSYa04T6N5RIZGBN2z2MT5IKGbFlbC8UrW0DxW7AYImQQcHtGl/m00QLVWutHQ
oVJYnFPlXTcHYvASLu+RhhsbDmxMgJJ0mcDpvsC4PjvB+TxywElgS70vE0XmLD+O
JtvsBslHZvPBKCOdT0MS+tgSOIfga+z1Z1g7+DVagf7quvmag8jfPioyKvxnK/Eg
sTUVi2ghzq8wm27ud/mIM7AY2qEORR8Go3TVB4HzWQgpZrt3i5MIlCaY504LzSRi
igHCzAPlHws+W0rB5N+er5/2pJKnfBSDiCiFAVtCLOZ7gLiMm0jhO2B6tUXHI/+M
RPjy02i59lINMRRev56GKtcd9qO/0kUJWdZTdA2XoS82ixPvZtXQpUpuL12ab+9E
aDK8Z4RHJYYfCT3Q5vNAXaiWQ+8PTWm2QgBR/bkwSWc+NpUFgNPN9PvQi8WEg5Um
AGMCAwEAAaNjMGEwHQYDVR0OBBYEFDZh4QB8iAUJUYtEbEf/GkzJ6k8SMB8GA1Ud
IwQYMBaAFDZh4QB8iAUJUYtEbEf/GkzJ6k8SMA8GA1UdEwEB/wQFMAMBAf8wDgYD
VR0PAQH/BAQDAgIEMA0GCSqGSIb3DQEBCwUAA4ICAQB8cMqTllHc8U+qCrOlg3H7
174lmaCsbo/bJ0C17JEgMLb4kvrqsXZs01U3mB/qABg/1t5Pd5AORHARs1hhqGIC
W/nKMav574f9rZN4PC2ZlufGXb7sIdJpGiO9ctRhiLuYuly10JccUZGEHpHSYM2G
tkgYbZba6lsCPYAAP83cyDV+1aOkTf1RCp/lM0PKvmxYN10RYsK631jrleGdcdkx
oSK//mSQbgcWnmAEZrzHoF1/0gso1HZgIn0YLzVhLSA/iXCX4QT2h3J5z3znluKG
1nv8NQdxei2DIIhASWfu804CA96cQKTTlaae2fweqXjdN1/v2nqOhngNyz1361mF
mr4XmaKH/ItTwOe72NI9ZcwS1lVaCvsIkTDCEXdm9rCNPAY10iTunIHFXRh+7KPz
lHGewCq/8TOohBRn0/NNfh7uRslOSZ/xKbN9tMBtw37Z8d2vvnXq/YWdsm1+JLVw
n6yYD/yacNJBlwpddla8eaVMjsF6nBnIgQOf9zKSe06nSTqvgwUHosgOECZJZ1Eu
zbH4yswbt02tKtKEFhx+v+OTge/06V+jGsqTWLsfrOCNLuA8H++z+pUENmpqnnHo
vaI47gC+TNpkgYGkkBT6B/m/U01BuOBBTzhIlMEZq9qkDWuM2cA5kW5V3FJUcfHn
w1IdYIg2Wxg7yHcQZemFQg==
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
MIICIjCCAaigAwIBAgIRAISp0Cl7DrWK5/8OgN52BgUwCgYIKoZIzj0EAwMwUjEc
MBoGA1UEAwwTS2V5IEF0dGVzdGF0aW9uIENBMTEQMA4GA1UECwwHQW5kcm9pZDET
MBEGA1UECgwKR29vZ2xlIExMQzELMAkGA1UEBhMCVVMwHhcNMjUwNzE3MjIzMjE4
WhcNMzUwNzE1MjIzMjE4WjBSMRwwGgYDVQQDDBNLZXkgQXR0ZXN0YXRpb24gQ0Ex
MRAwDgYDVQQLDAdBbmRyb2lkMRMwEQYDVQQKDApHb29nbGUgTExDMQswCQYDVQQG
EwJVUzB2MBAGByqGSM49AgEGBSuBBAAiA2IABCPaI3FO3z5bBQo8cuiEas4HjqCt
G/mLFfRT0MsIssPBEEU5Cfbt6sH5yOAxqEi5QagpU1yX4HwnGb7OtBYpDTB57uH5
Eczm34A5FNijV3s0/f0UPl7zbJcTx6xwqMIRq6NCMEAwDwYDVR0TAQH/BAUwAwEB
/zAOBgNVHQ8BAf8EBAMCAQYwHQYDVR0OBBYEFFIyuyz7RkOb3NaBqQ5lZuA0QepA
MAoGCCqGSM49BAMDA2gAMGUCMETfjPO/HwqReR2CS7p0ZWoD/LHs6hDi422opifH
EUaYLxwGlT9SLdjkVpz0UUOR5wIxAIoGyxGKRHVTpqpGRFiJtQEOOTp/+s1GcxeY
uR2zh/80lQyu9vAFCj6E4AXc+osmRg==
-----END CERTIFICATE-----
"""


TOKEN_PREFIX = "v1."             # token = "v1." + base64url(payload JSON) + "." + base64url(HMAC-SHA256)
TOKEN_MAX = 1024                # bytes; a real token is about 200


def _b64u(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64u(text):
    if not text or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for c in text):
        raise ValueError("bad token")
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make_token(key, payload):
    """An attestation token (v1.1, #452): "v1.<payload>.<mac>", both
    base64url without padding; mac = HMAC-SHA256(key, "v1." + payload part).
    payload: {"m": member, "k": 16 hex of the player key, "b": build label,
    "l": "tee"/"strongbox", "s": signer name, "exp": unix seconds}."""
    body = _b64u(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    mac = hmac.new(key, (TOKEN_PREFIX + body).encode(), hashlib.sha256).digest()
    return f"{TOKEN_PREFIX}{body}.{_b64u(mac)}"


def read_token(key, token, now=None):
    """The payload of a token made with key that has not expired.
    Raises ValueError("bad token") or ValueError("expired")."""
    if not isinstance(token, str) or len(token) > TOKEN_MAX or not token.startswith(TOKEN_PREFIX):
        raise ValueError("bad token")
    parts = token[len(TOKEN_PREFIX):].split(".")
    if len(parts) != 2:
        raise ValueError("bad token")
    want = hmac.new(key, (TOKEN_PREFIX + parts[0]).encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(_unb64u(parts[1]), want):
        raise ValueError("bad token")
    try:
        payload = json.loads(_unb64u(parts[0]))
    except (ValueError, UnicodeDecodeError):
        raise ValueError("bad token") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("exp"), int) \
            or not isinstance(payload.get("k"), str):
        raise ValueError("bad token")
    if (time.time() if now is None else now) >= payload["exp"]:
        raise ValueError("expired")
    return payload


def load_key_file(path):
    """32 secret bytes kept as base64 in path (one line, mode 0600);
    the file is made on first use."""
    try:
        with open(path) as f:
            text = f.read().strip()
    except FileNotFoundError:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return load_key_file(path)
        with os.fdopen(fd, "w") as f:
            f.write(base64.b64encode(secrets.token_bytes(32)).decode() + "\n")
        return load_key_file(path)
    try:
        key = base64.b64decode(text, validate=True)
    except ValueError:
        key = b""
    if len(key) != 32:
        raise ValueError(f"{path}: not 32 bytes of base64")
    return key


class AttestError(Exception):
    """A chain or key description that doesn't pass; the message is the
    short reason for the log ("chain", "revoked", "challenge", ...)."""


def _print_log(msg):
    print(f"[----] {msg}", flush=True)


# --- DER (only what the key description needs) ------------------------------

def der_read(b, i=0):
    """One DER element at b[i:]: (class, constructed, tag number, value, next i).
    Tag numbers of 31 and more use the long form (the key description's
    [704], [709], ...). Raises AttestError on anything malformed."""
    try:
        first = b[i]
        i += 1
        cls, constructed, tag = first >> 6, bool(first & 0x20), first & 0x1F
        if tag == 0x1F:
            tag = 0
            for _ in range(5):
                c = b[i]
                i += 1
                tag = (tag << 7) | (c & 0x7F)
                if not c & 0x80:
                    break
            else:
                raise AttestError("der")
        n = b[i]
        i += 1
        if n & 0x80:
            k = n & 0x7F
            if not 1 <= k <= 4:
                raise AttestError("der")
            n = int.from_bytes(b[i:i + k], "big")
            i += k
        if i + n > len(b):
            raise AttestError("der")
        return cls, constructed, tag, bytes(b[i:i + n]), i + n
    except IndexError:
        raise AttestError("der") from None


def der_items(b):
    """Every element directly inside a constructed value."""
    out, i = [], 0
    while i < len(b):
        cls, cons, tag, val, i = der_read(b, i)
        out.append((cls, cons, tag, val))
    return out


def der_int(v):
    return int.from_bytes(v, "big", signed=True) if v else 0


def authorization_list(b):
    """AuthorizationList: {tag number: the inner element's (tag, value)}
    from its [n] EXPLICIT fields."""
    out = {}
    for cls, _cons, tag, val in der_items(b):
        if cls == 2:                            # context-specific
            _c, _k, itag, ival, _n = der_read(val)
            out[tag] = (itag, ival)
    return out


def key_description(ext):
    """The attestation extension's DER as a dict (fields we use)."""
    _c, _k, tag, seq, _n = der_read(ext)
    if tag != 16:
        raise AttestError("key description")
    f = der_items(seq)
    if len(f) < 8:
        raise AttestError("key description")
    sw, hw = authorization_list(f[6][3]), authorization_list(f[7][3])
    d = dict(version=der_int(f[0][3]), security=der_int(f[1][3]),
             keymaster_version=der_int(f[2][3]), keymaster_security=der_int(f[3][3]),
             challenge=f[4][3], locked=None, boot=None, packages=[], digests=[])
    rot = hw.get(704) or sw.get(704)            # rootOfTrust
    if rot:
        r = der_items(rot[1])
        if len(r) >= 3:
            d["locked"] = r[1][3] != b"\x00"
            d["boot"] = BOOT_STATES.get(der_int(r[2][3]), "unknown")
    app = sw.get(709) or hw.get(709)            # attestationApplicationId (OCTET STRING of DER)
    if app:
        _c, _k, _t, a, _n = der_read(app[1])
        parts = der_items(a)
        if len(parts) >= 2:
            for _c2, _k2, _t2, info in der_items(parts[0][3]):
                p = der_items(info)
                if p:
                    d["packages"].append(p[0][3].decode("utf-8", "replace"))
            d["digests"] = [v.hex() for _c3, _k3, _t3, v in der_items(parts[1][3])]
    return d


# --- revocation list -------------------------------------------------------

class RevocationList:
    """Google's attestation revocation list
    ({"entries": {"<serial, lower-case hex>": {"status": "REVOKED", "reason": ...}}}),
    kept in a cache file and refreshed about daily in a background thread.
    Until one copy has loaded, nothing counts as revoked and `loaded` is
    False (the label then says "no revocation list")."""

    def __init__(self, path, url=STATUS_URL, fetch=None, clock=time.time, log=_print_log, background=True):
        self.path, self.url = path, url
        self.fetch = fetch or self._fetch
        self.clock, self.log, self.background = clock, log, background
        self._lock = threading.Lock()
        self._entries, self._fetched, self._next = {}, 0.0, 0.0
        self._busy = False
        try:
            with open(self.path, "rb") as f:
                self._entries, self._fetched = self._parse(f.read()), os.path.getmtime(self.path)
            self._next = self._fetched + STATUS_REFRESH_S
        except (OSError, ValueError):
            pass

    @property
    def loaded(self):
        return bool(self._fetched)

    def __len__(self):
        return len(self._entries)

    @staticmethod
    def _parse(data):
        entries = json.loads(data)["entries"]
        if not isinstance(entries, dict):
            raise ValueError("entries")
        return {str(k).lower(): v for k, v in entries.items()}

    def _fetch(self):
        req = urllib.request.Request(self.url, headers={"User-Agent": "rr3-attest"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read(8 * 1024 * 1024)

    def refresh(self):
        """Fetch now (the background thread, or a test)."""
        try:
            data = self.fetch()
            entries = self._parse(data)
            if self.path:
                tmp = self.path + ".tmp"
                with open(tmp, "wb") as f:
                    f.write(data)
                os.replace(tmp, self.path)
            with self._lock:
                self._entries, self._fetched = entries, self.clock()
                self._next = self._fetched + STATUS_REFRESH_S
            self.log(f"attestation revocation list: {len(entries)} entries")
        except Exception as e:      # network, JSON, disk: keep the old copy
            with self._lock:
                self._next = self.clock() + STATUS_RETRY_S
            self.log(f"attestation revocation list not fetched ({type(e).__name__}: {e}); "
                     + ("keeping the copy from " + time.strftime("%Y-%m-%d", time.gmtime(self._fetched))
                        if self._fetched else "none loaded yet"))
        finally:
            with self._lock:
                self._busy = False

    def maybe_refresh(self):
        with self._lock:
            if self._busy or self.clock() < self._next:
                return
            self._busy = True
        if self.background:
            threading.Thread(target=self.refresh, daemon=True).start()
        else:
            self.refresh()

    def revoked(self, serial):
        """The entry's reason if the certificate serial (int) is revoked, else None."""
        e = self._entries.get(format(serial, "x"))
        if e and str(e.get("status", "")).upper() == "REVOKED":
            return str(e.get("reason") or "revoked")
        return None


# --- chains ----------------------------------------------------------------

def load_roots(pem=ROOTS_PEM):
    """The root certificates as cryptography objects."""
    out, rest = [], pem
    while "-----BEGIN CERTIFICATE-----" in rest:
        start = rest.index("-----BEGIN CERTIFICATE-----")
        end = rest.index("-----END CERTIFICATE-----", start) + len("-----END CERTIFICATE-----")
        out.append(x509.load_pem_x509_certificate(rest[start:end].encode()))
        rest = rest[end:]
    return out


def _spki(cert):
    return cert.public_key().public_bytes(serialization.Encoding.DER,
                                          serialization.PublicFormat.SubjectPublicKeyInfo)


def oid_str(v):
    """An OBJECT IDENTIFIER's content bytes as dotted text."""
    if not v:
        raise AttestError("der")
    out, n = [], 0
    for c in v:
        n = (n << 7) | (c & 0x7F)
        if not c & 0x80:
            out.append(n)
            n = 0
    if not out or v[-1] & 0x80:
        raise AttestError("der")
    first = min(out[0] // 40, 2)
    return ".".join(str(x) for x in [first, out[0] - 40 * first] + out[1:])


def _der_time(tag, v):
    """UTCTime (23) or GeneralizedTime (24) as a Unix time; None if unreadable."""
    t = v.decode("ascii", "replace").rstrip("Z")
    if tag == 23:
        if len(t) < 10 or not t[:10].isdigit():
            return None
        y = int(t[:2])
        t = ("19" if y >= 50 else "20") + t
    t = t.split(".")[0]
    if len(t) < 12 or not t[:12].isdigit():
        return None
    sec = int(t[12:14]) if len(t) >= 14 and t[12:14].isdigit() else 0
    try:
        return calendar.timegm((int(t[:4]), int(t[4:6]), int(t[6:8]), int(t[8:10]), int(t[10:12]), sec))
    except (ValueError, OverflowError):
        return None


# signature algorithm OID -> (key type, hash)
SIG_ALGS = {
    "1.2.840.10045.4.3.2": ("ec", "SHA256"), "1.2.840.10045.4.3.3": ("ec", "SHA384"),
    "1.2.840.10045.4.3.4": ("ec", "SHA512"),
    "1.2.840.113549.1.1.11": ("rsa", "SHA256"), "1.2.840.113549.1.1.12": ("rsa", "SHA384"),
    "1.2.840.113549.1.1.13": ("rsa", "SHA512"),
}


class Cert:
    """The parts of one X.509 certificate the chain check uses, read by our
    own DER reader (v1.3), so a certificate the cryptography package
    refuses to parse can still be checked. Fields are taken from the signed
    tbsCertificate bytes, which the issuer's signature covers."""

    def __init__(self, der):
        _c, _k, tag, cert, end = der_read(der)
        if tag != 16 or end != len(der):
            raise AttestError("der")
        parts, i = [], 0
        while i < len(cert):
            start = i
            cls, cons, tag, val, i = der_read(cert, i)
            parts.append((cls, tag, val, cert[start:i]))
        if len(parts) != 3 or parts[0][1] != 16 or parts[2][1] != 3 or not parts[2][2]:
            raise AttestError("der")
        self.tbs = parts[0][3]
        alg = der_items(parts[1][2])
        self.sig_oid = oid_str(alg[0][3]) if alg and alg[0][2] == 6 else ""
        self.signature = parts[2][2][1:]            # BIT STRING: drop the unused-bits byte
        f, i, raw = [], 0, parts[0][2]
        while i < len(raw):
            start = i
            cls, cons, tag, val, i = der_read(raw, i)
            f.append((cls, tag, val, raw[start:i]))
        if f and f[0][0] == 2 and f[0][1] == 0:     # [0] version
            f = f[1:]
        if len(f) < 6 or f[0][1] != 2:
            raise AttestError("der")
        self.serial_number = der_int(f[0][2])
        self.issuer, self.subject, self.spki = f[2][3], f[4][3], f[5][3]
        times = der_items(f[3][2])
        self.not_before = _der_time(times[0][2], times[0][3]) if times else None
        self.extensions = {}
        for cls, tag, val, _raw in f[6:]:
            if cls == 2 and tag == 3:               # [3] EXPLICIT extensions
                _c, _k, _t, exts, _n = der_read(val)
                for _c2, _k2, _t2, e in der_items(exts):
                    ef = der_items(e)
                    if len(ef) >= 2 and ef[0][2] == 6:
                        self.extensions[oid_str(ef[0][3])] = ef[-1][3]

    def public_key(self):
        try:
            return serialization.load_der_public_key(self.spki)
        except Exception as e:                      # ValueError, UnsupportedAlgorithm, ...
            raise AttestError("chain: public key") from e

    def spki_der(self):
        """The public key re-encoded, to compare with a root's."""
        try:
            return _spki(self)
        except AttestError:
            return self.spki


def name_key(raw):
    """A Name's DER as a tuple of RDNs of (OID, text), so names that differ
    only in string type (PrintableString vs UTF8String) match, as
    cryptography's Name equality did before v1.3."""
    try:
        out = []
        for _c, _k, _t, rdn in der_items(der_read(raw)[3]):
            atts = []
            for _c2, _k2, _t2, atv in der_items(rdn):
                f = der_items(atv)
                if len(f) < 2 or f[0][2] != 6:
                    return raw
                enc = "utf-16-be" if f[1][2] == 30 else "utf-32-be" if f[1][2] == 28 else "utf-8"
                atts.append((oid_str(f[0][3]), f[1][3].decode(enc, "replace")))
            out.append(tuple(sorted(atts)))
        return tuple(out)
    except AttestError:
        return raw


def _signed_by(cert, issuer_key):
    """True if cert's signature verifies with issuer_key (no name check)."""
    alg = SIG_ALGS.get(cert.sig_oid)
    if not alg:
        return False
    h = getattr(hashes, alg[1])()
    try:
        if alg[0] == "ec" and isinstance(issuer_key, ec.EllipticCurvePublicKey):
            issuer_key.verify(cert.signature, cert.tbs, ec.ECDSA(h))
        elif alg[0] == "rsa" and isinstance(issuer_key, rsa.RSAPublicKey):
            issuer_key.verify(cert.signature, cert.tbs, padding.PKCS1v15(), h)
        else:
            return False
    except Exception:                               # InvalidSignature, ValueError, ...
        return False
    return True


def _parse_error(e):
    """A short form of the cryptography parser's error for the log:
    "InvalidValue at TbsCertificate::serial"."""
    m = " ".join(str(e).split())
    kind = re.search(r"kind: (\w+)", m)
    loc = re.findall(r'"([^"]+)"', m)
    if kind:
        return kind.group(1) + (" at " + loc[-1] if loc else "")
    return m[:60]


def verify_chain(ders, roots, revocation=None, now=None, notes=None):
    """Check a chain (leaf first, DER bytes each) up to one of roots.
    Returns the leaf (a Cert); raises AttestError with the reason.
    notes (a list) gets one line per certificate that the cryptography
    package refused to parse but our reader accepted (v1.3)."""
    if not ders or len(ders) > CHAIN_MAX or any(not d or len(d) > CERT_MAX for d in ders):
        raise AttestError("chain size")
    now = time.time() if now is None else now
    certs = []
    for i, d in enumerate(ders):
        strict = ""
        try:
            with warnings.catch_warnings():         # e.g. a negative serial
                warnings.simplefilter("ignore")
                x509.load_der_x509_certificate(d)
        except Exception as e:                      # ValueError, InvalidVersion, ...
            strict = _parse_error(e)
        try:
            certs.append(Cert(d))
        except (AttestError, IndexError, ValueError, UnicodeError):
            raise AttestError(f"chain: bad certificate {i} ({strict or 'der'})") from None
        if strict and notes is not None:
            notes.append(f"certificate {i}: {strict}")
    for i in range(len(certs) - 1):
        if (name_key(certs[i].issuer) != name_key(certs[i + 1].subject)
                or not _signed_by(certs[i], certs[i + 1].public_key())):
            raise AttestError(f"chain: certificate {i} not issued by {i + 1}")
    top, root_keys = certs[-1], {_spki(r) for r in roots}
    if top.spki_der() not in root_keys:
        for r in roots:
            if name_key(top.issuer) == name_key(r.subject.public_bytes()) and _signed_by(top, r.public_key()):
                break
        else:
            raise AttestError("chain: unknown root")
    # The leaf's dates are the app's own choice. A CA certificate's end date
    # is not checked (v1.2, #452): factory attestation certificates are never
    # renewed, so older phones carry expired ones; retired keys are on the
    # revocation list instead.
    for i, c in enumerate(certs[1:], 1):
        if c.not_before is not None and c.not_before - SKEW_S > now:
            raise AttestError(f"chain: certificate {i} not yet valid")
    if revocation is not None:
        for c in certs:
            why = revocation.revoked(c.serial_number)
            if why:
                raise AttestError(f"revoked ({why.lower()})")
    return certs[0]


def leaf_description(leaf):
    ext = leaf.extensions.get(KEY_DESCRIPTION_OID)
    if ext is None:
        raise AttestError("no key description")
    return key_description(ext)


def challenge_for(nonce, secret):
    """SHA-256(nonce || secret), both raw bytes: what the phone passes to
    setAttestationChallenge()."""
    return hashlib.sha256(nonce + secret).digest()


# --- the server's state ----------------------------------------------------

class Attestation:
    """Challenges, checks and the per-player result for one server.

    state_path: JSON file {player key: result}, private (written 0600).
    trusted: callable sha256 hex -> key name or None (TrustedSigs.get).
    Thread-safe; the server calls new_nonce() and check() from request
    threads."""

    def __init__(self, state_path, revocation=None, trusted=None, roots=None, clock=time.time,
                 log=_print_log, ttl_s=TTL_S):
        if not AVAILABLE:
            raise RuntimeError(WHY_NOT)
        self.state_path, self.revocation, self.trusted = state_path, revocation, trusted
        self.roots = roots if roots is not None else load_roots()
        self.clock, self.log, self.ttl_s = clock, log, ttl_s
        self._lock = threading.Lock()
        self._nonces = {}               # hex -> issue time
        self.state = {}
        try:
            with open(state_path) as f:
                self.state = json.load(f)
        except (OSError, ValueError):
            pass

    def new_nonce(self):
        n = secrets.token_hex(16)
        now = self.clock()
        with self._lock:
            for k in [k for k, t in self._nonces.items() if now - t > NONCE_TTL_S]:
                del self._nonces[k]
            while len(self._nonces) >= NONCE_MAX:
                self._nonces.pop(next(iter(self._nonces)))
            self._nonces[n] = now
        if self.revocation is not None:
            self.revocation.maybe_refresh()
        return n

    def _take_nonce(self, n):
        with self._lock:
            t = self._nonces.pop(n, None)
        return t is not None and self.clock() - t <= NONCE_TTL_S

    def check(self, nonce_hex, secret_hex, chain):
        """One proof: chain (list of DER bytes, leaf first) for a player
        whose stored secret is secret_hex. Returns the result dict
        {"ok", "bound", "reason", "key", "level", "locked", "boot", "time"}.
        bound: the challenge matched, so the proof (good or bad) really
        comes from the phone holding that secret. The server records only
        bound results: anyone can send a chain naming any Android id, and
        that must not overwrite the player's state."""
        r = dict(ok=False, bound=False, reason="", key=None, level=None, locked=None, boot=None,
                 time=self.clock())
        try:
            if not isinstance(nonce_hex, str) or not self._take_nonce(nonce_hex):
                raise AttestError("nonce")
            if not secret_hex:
                raise AttestError("no secret")
            notes = []
            try:
                leaf = verify_chain(chain, self.roots, self.revocation, self.clock(), notes)
            finally:
                if notes:
                    self.log("attest: lenient parse: " + "; ".join(notes))
            d = leaf_description(leaf)
            r.update(level=SECURITY_LEVELS.get(d["security"], "unknown"), locked=d["locked"], boot=d["boot"])
            if d["challenge"] != challenge_for(bytes.fromhex(nonce_hex), bytes.fromhex(secret_hex)):
                raise AttestError("challenge")
            r["bound"] = True
            if d["security"] not in (1, 2) or d["keymaster_security"] not in (1, 2):
                raise AttestError("software key")
            if PACKAGE not in d["packages"]:
                raise AttestError("package " + ",".join(d["packages"])[:40])
            names = [n for n in (self.trusted(x) if self.trusted else None for x in d["digests"]) if n]
            if not names:
                raise AttestError("signed by " + ",".join(x[:8] for x in d["digests"]) + "..")
            r.update(ok=True, key=names[0])
        except AttestError as e:
            r["reason"] = str(e)
        except ValueError as e:         # bad hex and the like
            r["reason"] = f"bad input ({e})"
        return r

    def record(self, player, result):
        """Keep result as player's latest; written at once (a few per player a day)."""
        with self._lock:
            self.state[player] = result
            data = json.dumps(self.state, indent=1, sort_keys=True)
        if self.state_path:
            os.makedirs(os.path.dirname(os.path.abspath(self.state_path)), exist_ok=True)
            tmp = self.state_path + ".tmp"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(data)
            os.replace(tmp, self.state_path)

    def label(self, player):
        """The log label for player's requests: "devel (tee, locked)",
        "fail (reason)" or "none" (nothing within ttl_s)."""
        with self._lock:
            r = self.state.get(player)
        if not r or self.clock() - r.get("time", 0) > self.ttl_s:
            return "none"
        if not r.get("ok"):
            return f"fail ({r.get('reason')})"
        lock = "locked" if r.get("locked") else "unlocked" if r.get("locked") is False else "lock?"
        extra = "" if (self.revocation is None or self.revocation.loaded) else ", no revocation list"
        return f"{r.get('key')} ({r.get('level')}, {lock}{extra})"

    def player_for(self, prefix):
        """The player key whose hex starts with prefix (16 hex, a token's
        "k"), among recorded players; None if none (v1.1)."""
        with self._lock:
            return next((k for k in self.state if k[2:2 + len(prefix)] == prefix), None) if prefix else None

    def attested(self, player):
        """True while player's latest proof passed within ttl_s."""
        with self._lock:
            r = self.state.get(player)
        return bool(r and r.get("ok") and self.clock() - r.get("time", 0) <= self.ttl_s)


def parse_request(body):
    """POST /prr/attest body: JSON {"v": 1, "nonce": hex, "android_id": 16 hex,
    "chain": [base64 DER, ...]} -> (nonce, android_id, [DER, ...]); ValueError if bad."""
    d = json.loads(body)
    if not isinstance(d, dict) or d.get("v") != 1:
        raise ValueError("version")
    nonce, aid, chain = d.get("nonce"), d.get("android_id"), d.get("chain")
    if not (isinstance(nonce, str) and len(nonce) == 32 and all(c in "0123456789abcdef" for c in nonce)):
        raise ValueError("nonce")
    if not (isinstance(aid, str) and len(aid) == 16 and all(c in "0123456789abcdef" for c in aid)):
        raise ValueError("android_id")
    if not isinstance(chain, list) or not 1 <= len(chain) <= CHAIN_MAX:
        raise ValueError("chain")
    try:
        ders = [base64.b64decode(c, validate=True) for c in chain]
    except (TypeError, ValueError):
        raise ValueError("chain base64") from None
    return nonce, aid, ders
