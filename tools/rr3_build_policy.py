#!/usr/bin/env python3
"""Build allowlist and build gate for PRR servers (issue #242).

Part of Project Real Resurrection's work on Real Racing 3. Not affiliated
with, endorsed or supported by Electronic Arts.

One portable module: no module-level state. Everything a server needs is
passed in (allowlist path, cache size and time, clock, logger), so any of
our servers (CC, MP, devel's assets server, a future one) plugs it in with
a few lines (docs/build-policy.md):

    allowlist = BuildAllowlist("builds-allowed.txt")
    gate = BuildGate(allowlist)
    ok, build, cached = gate.check(player, label, report_present)

The allowlist file is UTF-8, one exact ``PRR bNN-channel`` (Android) or
``PRR iNN-channel`` (iOS, v1.2) label per line;
blank lines and lines starting with ``#`` are ignored. The file is checked
at most once per refresh interval, not on every request or UDP datagram.

Label extraction stays next to each protocol's parser
(rr3_cc_blob.build_tag, rr3_mp_server.build_tag_from_hello); the gate only
decides on labels.

v1.0 (issue #242): BuildGate owns the decision and the same-player cache
that were inline in rr3_cc_server.py v5.22; logger and clock are injected.
v1.1 (issue #242): AdmitFile shares admitted IPs between processes (CC
writes, the asset server reads); ip_key() normalises an address.
v1.2 (issue #299): labels may also be iOS builds, ``PRR iNN-channel``
(ios/tools/rr3_ios_build_tag.py); Android labels are unchanged.
v1.3 (issue #332): Blocklist, single players (``member N``) and addresses
(``ip A.B.C.D`` or a range ``ip A.B.C.0/24``, IPv6 too) both servers refuse;
re-read when the file changes, a missing file blocks nobody.
"""
import ipaddress
import json
import os
import re
import threading
import time

VERSION = "1.3"

BUILD_TAG_RE = re.compile(r"PRR [bi][0-9]{2,}-(?:alpha|beta|stable)\Z")
BUILD_TAG_TEXT_RE = re.compile(r"\[(PRR [bi][0-9]{2,}-(?:alpha|beta|stable))\]")

CACHE_S = 15 * 60       # a verified build is reused this long for the same key
CACHE_MAX = 10000       # keys kept at most (oldest use dropped first)


ADMIT_WRITE_S = 60      # an IP already in the admit file is rewritten at most this often


def ip_key(ip):
    """The gate's key for a client address: "ip:" + the address, IPv4-mapped
    IPv6 (::ffff:1.2.3.4) as plain IPv4, IPv6 compressed and lower case."""
    ip = str(ip).strip()
    try:
        a = ipaddress.ip_address(ip)
        if a.version == 6 and a.ipv4_mapped:
            a = a.ipv4_mapped
        ip = a.compressed
    except ValueError:
        pass
    return "ip:" + ip


def _print_log(msg):
    print(f"[----] {msg}", flush=True)


class BuildAllowlist:
    """An exact-match allowlist that reloads atomically replaced files.

    A missing, unreadable, or invalid file denies all labels after startup.
    The initial load raises so a typo cannot silently start enforcement with
    an unexpected policy. A valid empty file intentionally denies every build.
    """

    def __init__(self, path, refresh_s=1.0, clock=time.monotonic, log=_print_log):
        self.path = os.fspath(path)
        self.refresh_s = max(0.1, float(refresh_s))
        self.clock, self.log = clock, log
        self._lock = threading.Lock()
        self._allowed = frozenset()
        self._stamp = None
        self._next_check = 0.0
        self._error = None
        self._refresh(force=True, initial=True)

    @property
    def count(self):
        self._refresh()
        return len(self._allowed)

    def allows(self, build):
        """Return true only for an exact, currently allowed build label."""
        self._refresh()
        return self._error is None and isinstance(build, str) and build in self._allowed

    def _read(self):
        st = os.stat(self.path)
        stamp = (st.st_mtime_ns, st.st_size)
        with open(self.path, "r", encoding="utf-8-sig") as f:
            text = f.read()
        allowed = set()
        for n, line in enumerate(text.splitlines(), 1):
            label = line.strip()
            if not label or label.startswith("#"):
                continue
            if not BUILD_TAG_RE.fullmatch(label):
                raise ValueError(f"line {n}: invalid build label {label!r}")
            allowed.add(label)
        return frozenset(allowed), stamp

    def _refresh(self, force=False, initial=False):
        now = self.clock()
        if not force and now < self._next_check:
            return
        with self._lock:
            now = self.clock()
            if not force and now < self._next_check:
                return
            self._next_check = now + self.refresh_s
            try:
                allowed, stamp = self._read()
            except (OSError, UnicodeError, ValueError) as e:
                if initial:
                    raise ValueError(f"build allowlist {self.path}: {e}") from e
                self._allowed = frozenset()
                self._stamp = None
                msg = f"build allowlist {self.path}: {e}; denying every build"
                if msg != self._error:
                    self.log(msg)
                self._error = msg
                return
            changed = allowed != self._allowed or self._error is not None
            self._allowed, self._stamp = allowed, stamp
            self._error = None
            if changed and not initial:
                self.log(f"reloaded build allowlist {self.path}: {len(allowed)} allowed build(s)")


def _ip(ip):
    """ip as an ipaddress object (IPv4-mapped IPv6 as IPv4), or None."""
    try:
        a = ipaddress.ip_address(str(ip).strip())
    except ValueError:
        return None
    return a.ipv4_mapped if a.version == 6 and a.ipv4_mapped else a


class Blocklist:
    """Players and addresses a server refuses (issue #332).

    The file is UTF-8, one rule per line; ``#`` starts a comment (the
    reason), blank lines are skipped::

        member 1025          # cheated times
        ip 203.0.113.7       # flood
        ip 203.0.113.0/24

    Unlike the allowlist it fails open: a missing file blocks nobody, a
    line that can't be read is logged and skipped (the others still
    apply), and an unreadable file keeps the last good rules. The file is
    checked at most once per refresh interval. Thread-safe.
    """

    def __init__(self, path, refresh_s=1.0, clock=time.monotonic, log=_print_log):
        self.path = os.fspath(path)
        self.refresh_s = max(0.1, float(refresh_s))
        self.clock, self.log = clock, log
        self._lock = threading.Lock()
        self._members = frozenset()
        self._nets = ()
        self._stamp = None
        self._next_check = 0.0
        self._error = None
        self._refresh(force=True, initial=True)

    @property
    def counts(self):
        """(member rules, ip rules) now in force."""
        self._refresh()
        return len(self._members), len(self._nets)

    def describe(self):
        m, n = self.counts
        return f"{m} member(s), {n} ip rule(s)"

    def member(self, member):
        """The rule ("member N") if member is blocked, else None."""
        self._refresh()
        try:
            member = int(member)
        except (TypeError, ValueError):
            return None
        return f"member {member}" if member in self._members else None

    def ip(self, ip):
        """The rule ("ip A.B.C.D" or "ip A.B.C.0/24") if ip is blocked, else None."""
        self._refresh()
        if not self._nets:
            return None
        a = _ip(ip)
        if a is None:
            return None
        for net in self._nets:
            if a.version == net.version and a in net:
                return "ip " + (str(net.network_address) if net.num_addresses == 1 else str(net))
        return None

    def _read(self):
        st = os.stat(self.path)
        stamp = (st.st_mtime_ns, st.st_size)
        with open(self.path, "r", encoding="utf-8-sig") as f:
            text = f.read()
        members, nets, bad = set(), [], []
        for n, line in enumerate(text.splitlines(), 1):
            rule = line.split("#", 1)[0].split()
            if not rule:
                continue
            what = rule[0].lower()
            try:
                if len(rule) != 2:
                    raise ValueError
                if what == "member":
                    m = int(rule[1])
                    if m < 1:
                        raise ValueError
                    members.add(m)
                elif what == "ip":
                    net = ipaddress.ip_network(rule[1], strict=False)
                    if net.version == 6 and net.num_addresses == 1 and net.network_address.ipv4_mapped:
                        net = ipaddress.ip_network(net.network_address.ipv4_mapped)
                    nets.append(net)
                else:
                    raise ValueError
            except ValueError:
                bad.append(n)
        return frozenset(members), tuple(nets), bad, stamp

    def _refresh(self, force=False, initial=False):
        now = self.clock()
        if not force and now < self._next_check:
            return
        with self._lock:
            now = self.clock()
            if not force and now < self._next_check:
                return
            self._next_check = now + self.refresh_s
            try:
                st = os.stat(self.path)
            except FileNotFoundError:
                if self._stamp is not None or initial:
                    if self._members or self._nets:
                        self.log(f"blocklist {self.path} removed: nobody blocked")
                    self._members, self._nets, self._stamp = frozenset(), (), None
                self._error = None
                return
            except OSError as e:
                self._fail(e)
                return
            if (st.st_mtime_ns, st.st_size) == self._stamp and self._error is None:
                return
            try:
                members, nets, bad, stamp = self._read()
            except (OSError, UnicodeError) as e:
                self._fail(e)
                return
            self._members, self._nets, self._stamp, self._error = members, nets, stamp, None
            for n in bad:
                self.log(f"blocklist {self.path}: line {n} not understood, skipped")
            if not initial:
                self.log(f"reloaded blocklist {self.path}: {len(members)} member(s), {len(nets)} ip rule(s)")

    def _fail(self, e):
        """Unreadable: keep the last good rules, log once."""
        msg = f"blocklist {self.path}: {e}; keeping the last rules"
        if msg != self._error:
            self.log(msg)
        self._error = msg


class BuildGate:
    """The whole allow/deny decision for one server.

    allowlist: anything with ``allows(label)`` and ``count`` (a
    BuildAllowlist). key: any string naming the client (a private player
    key, an IP); "unknown" or None is never cached. Thread-safe.
    """

    def __init__(self, allowlist, cache_s=CACHE_S, cache_max=CACHE_MAX, clock=time.monotonic,
                 admit_file=None):
        self.allowlist = allowlist
        self.admit_file = admit_file    # an AdmitFile shared with other processes, or None
        self.cache_s, self.cache_max = float(cache_s), int(cache_max)
        self.clock = clock
        self._lock = threading.Lock()
        self._seen = {}                 # key -> (last allowed label, last use time)

    @property
    def count(self):
        return self.allowlist.count

    def allows(self, label):
        """An exact label is currently allowed (no cache)."""
        return self.allowlist.allows(label)

    check_label = allows

    def check(self, key, label, report_present):
        """Decide for one request: (allowed, build, cached).

        label: the label the request carries, else None. report_present:
        the request carries the place a label would be in (CC subsync 68),
        even if no valid label was read from it.
        - a label: allowed if on the list; an allowed one is remembered
          for key;
        - no report at all: key's remembered label, if still fresh and
          still on the list (cached=True);
        - a report without a valid label: denied.
        """
        if label is not None:
            ok = self.allowlist.allows(label)
            if ok:
                self.remember(key, label)
            return ok, label, False
        if report_present:
            return False, None, False
        build = self.recall(key)
        if build is None:
            return False, None, False
        return self.allowlist.allows(build), build, True

    def remember(self, key, label):
        if key in (None, "unknown"):
            return
        with self._lock:
            self._seen.pop(key, None)
            self._seen[key] = (label, self.clock())
            while len(self._seen) > self.cache_max:
                self._seen.pop(next(iter(self._seen)))

    def recall(self, key):
        """key's remembered label if used within cache_s (refreshes it), else None."""
        if key in (None, "unknown"):
            return None
        now = self.clock()
        with self._lock:
            item = self._seen.pop(key, None)
            if item is None:
                return None
            label, used = item
            if now - used > self.cache_s:
                return None
            self._seen[key] = (label, now)
            return label

    def admit(self, key, label):
        """Remember an allowed key here and, if set, in the admit file."""
        self.remember(key, label)
        if self.admit_file is not None:
            self.admit_file.add(key, label)

    def check_cached(self, key):
        """(allowed, build) from key's remembered label only, for a channel
        that carries no label (the MP game port, asset downloads): this
        gate's cache first, then the admit file. The label must still be
        on the list."""
        build = self.recall(key)
        if build is None and self.admit_file is not None:
            build = self.admit_file.get(key)
        return (build is not None and self.allowlist.allows(build)), build


class AdmitFile:
    """Admitted client keys shared between processes through one JSON file:
    {"version": 1, "keys": {"ip:1.2.3.4": ["PRR b48-beta", unix time]}}.

    One process writes (the server that sees build labels, e.g. CC); any
    number read. Writes replace the file atomically (temp file + rename);
    entries older than ttl_s are dropped. A missing or broken file reads as
    empty (nobody admitted). Uses wall time (time.time) because the time is
    compared across processes.
    """

    def __init__(self, path, ttl_s=CACHE_S, write_s=ADMIT_WRITE_S, clock=time.time, log=_print_log):
        self.path = os.fspath(path)
        self.ttl_s, self.write_s = float(ttl_s), float(write_s)
        self.clock, self.log = clock, log
        self._lock = threading.Lock()
        self._keys = {}
        self._stamp = None
        self._error = None

    def _load(self):
        """Re-read the file if it changed; keeps the last good copy on error."""
        try:
            st = os.stat(self.path)
        except OSError:
            self._keys, self._stamp = {}, None
            return
        stamp = (st.st_mtime_ns, st.st_size)
        if stamp == self._stamp:
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            keys = {k: (str(v[0]), float(v[1])) for k, v in data.get("keys", {}).items()}
        except (OSError, ValueError, TypeError, IndexError, AttributeError) as e:
            msg = f"admit file {self.path}: {e}; nobody admitted"
            if msg != self._error:
                self.log(msg)
            self._error = msg
            self._keys, self._stamp = {}, stamp
            return
        self._keys, self._stamp, self._error = keys, stamp, None

    def add(self, key, label):
        """Record key as admitted with label now (written at most every write_s)."""
        if key in (None, "unknown", "ip:"):
            return
        now = self.clock()
        with self._lock:
            self._load()
            old = self._keys.get(key)
            if old and old[0] == label and now - old[1] < self.write_s:
                return
            keys = {k: v for k, v in self._keys.items() if now - v[1] <= self.ttl_s}
            keys[key] = (label, now)
            tmp = f"{self.path}.{os.getpid()}.tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump({"version": 1, "keys": {k: list(v) for k, v in keys.items()}}, f)
                os.replace(tmp, self.path)
            except OSError as e:
                self.log(f"admit file {self.path}: {e}; not written")
                return
            self._keys, self._stamp = keys, None

    def get(self, key):
        """key's label if admitted within ttl_s, else None."""
        now = self.clock()
        with self._lock:
            self._load()
            item = self._keys.get(key)
        if item is None or now - item[1] > self.ttl_s:
            return None
        return item[0]
