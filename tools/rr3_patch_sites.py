#!/usr/bin/env python3
"""Every libRealRacing3.so address range our patch tools write, so parallel
patches don't overlap (tables/lib-patch-sites.csv; CLAUDE.md "Patch sites
don't overlap"). develified.apk only (one APK for every GPU).

The table is not written by hand: `update` runs each tool's `patch` on the
develified lib once per variant (every `--laps` mode, every `--parts` part, ...),
compares the output with develified and records each changed byte range. Hand
patches with no tool yet, and community patches already in develified that no
tool may overwrite (tool "develified"), are listed in HAND below.

  rr3_patch_sites.py update   rewrite tables/lib-patch-sites.csv
  rr3_patch_sites.py check    fail if the table is out of date (a tool's
                              addresses changed), two tools overlap, or a
                              patch tool (a tools/*.py with `contents()`)
                              is missing from VARIANTS
  rr3_patch_sites.py find START [END]
                              which tools write in 0xSTART..0xEND (planned
                              sites for a new patch, at design time)
  rr3_patch_sites.py caves [--kind code|data]
                              each cave in tables/lib-code-caves.csv:
                              what uses it and the free ranges left (the
                              used ranges of lib-patch-sites.csv taken out)

`check` also checks tables/lib-code-caves.csv against the develified lib (size,
develified bytes, inside .text for `code` / .rodata for `data`, no two caves
overlap) and fails when a tool writes in a cave whose `requires` (e.g.
"rr3_debug_menu.py nosales") is not in that tool's REQUIRES list. Free cave
space is always computed, never written in the table. A `data` cave is not
executable: never put code there. Free space comes from the compare below,
so bytes a tool writes with their develified value (zeros in zero padding) look
free: read the tool's own develified check before using the edge of a used range.

Variants of one tool may share bytes (`--laps 9` and `--laps best` are
alternatives); only ranges of different tools are checked for overlap.
A byte that a patch happens to set to its develified value is not seen by the
compare, so a range can look a few bytes shorter than what the tool owns;
ranges are widened to whole 4-byte words (one arm64 instruction) and ranges
closer than GAP bytes are joined to cover that.
"""
import argparse
import csv
import gzip
import hashlib
import importlib
import os
import re
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEVELIFIED = os.path.join(ROOT, "game", "develified-libRealRacing3.so.gz")
TABLE = os.path.join(ROOT, "tables", "lib-patch-sites.csv")
CAVES = os.path.join(ROOT, "tables", "lib-code-caves.csv")
GAP = 16
FIELDS = ["tool", "patch", "start", "end", "bytes"]
CAVE_FIELDS = ["start", "end", "size", "kind", "what", "why_dead", "requires", "checked", "source",
               "develified_sha256"]
SECTION = {"code": ".text", "data": ".rodata"}

# (tool, patch name, extra `patch` arguments[, arguments of a first patch it
# needs, or (other tool, its arguments)]). One row group per variant; a
# variant with a first patch is compared with that patch's output, not with
# develified.
VARIANTS = [("rr3_tt_laps.py", f"laps={n}", ["--laps", n])
            for n in ("2", "3", "5", "9", "17", "unlimited", "reset")]
VARIANTS += [("rr3_tt_laps.py", f"laps=best-v{v}", ["--laps", "best", "--best-version", v])
             for v in ("2", "3", "4", "5")]
VARIANTS += [("rr3_mtx.py", p, ["--parts", p]) for p in ("open", "buy", "valid", "list", "online")]
VARIANTS += [("rr3_drive_cost.py", "free-drives", [])]
VARIANTS += [("rr3_debug_menu.py", p, ["--parts", p]) for p in ("nosales", "race", "noskillcalc", "modes", "nophysfix", "nowin")]
VARIANTS += [("rr3_debug_menu.py", f"menu-v{v}", ["--parts", "menu", "--menu-version", v]) for v in ("1", "2")]
VARIANTS += [("rr3_debug_menu.py", f"trim-v{v}", ["--parts", "trim", "--trim-version", v], ["--parts", "nosales"])
             for v in ("1", "2", "3", "4", "5", "6", "7")]
VARIANTS += [("rr3_debug_menu.py", f"settings-v{v}", ["--parts", "settings", "--settings-version", v], ["--parts", "nosales"])
             for v in ("1", "2", "3", "4", "5")]
# Longest host (23 characters) so the whole string fields show up.
VARIANTS += [("rr3_cc_local.py", "host", ["--host", "h" * 23, "--port", "8080"]),
             ("rr3_cc_local.py", "host-https", ["--host", "h" * 23, "--port", "443"]),
             ("rr3_cc_local.py", "cdn", ["--parts", "cdn", "--cdn-host", "h" * 25]),
             ("rr3_cc_local.py", "fallback", ["--parts", "fallback", "--fallback-host", "h" * 25])]
VARIANTS += [("rr3_login_popup.py", "no-login-popup", [])]
VARIANTS += [("rr3_selector_times.py", f"selector-times-v{v}", ["--version", v]) for v in ("1", "2")]
VARIANTS += [("rr3_omp.py", f"nosocial-v{v}", ["--parts", "nosocial", "--nosocial-version", v]) for v in ("1", "2")]
# Longest master server host (26 characters) so the whole string shows up.
VARIANTS += [("rr3_omp.py", "host", ["--parts", "host", "--mp-host", "h" * 26])]
# Second host (22 characters) and a port with every bit of 60000 flipped (0x159f).
VARIANTS += [("rr3_omp.py", "host2-port", ["--parts", "host", "--mp-host", "h" * 26, "--mp-host2", "h" * 22,
                                           "--mp-port", str(0xEA60 ^ 0xFFFF)])]
VARIANTS += [("rr3_omp.py", f"stock-v{v}", ["--parts", "stock", "--stock-version", v]) for v in ("1", "2")]
VARIANTS += [("rr3_omp.py", "nolevel-v1", ["--parts", "nolevel"])]
VARIANTS += [("rr3_username.py", f"username-v{v}", ["--version", v], ("rr3_debug_menu.py", ["--parts", "nosales"]))
             for v in ("1", "2", "3", "4", "5")]
VARIANTS += [("rr3_friends_mail.py", "friends-mail", [])]
# Longest tag (127 characters) so the whole field shows up.
VARIANTS += [("rr3_build_tag.py", "build-tag", ["--tag", "x" * 127])]
VARIANTS += [("rr3_prr_secret.py", "prr-secret", [])]
# prr-login v2 rows retired 2026-11-09 (#145): its Community sites
# (0xd6d710, 0xd6de34) went to rr3_community.py; v3 = v2 without them.
VARIANTS += [("rr3_prr_login.py", f"prr-login-v{v}", ["--version", v]) for v in ("1", "3")]
VARIANTS += [("rr3_prr_social.py", f"prr-social-v{v}", ["--version", v]) for v in ("1", "2")]
VARIANTS += [("rr3_discount_popup.py", "discount-popup", [])]
VARIANTS += [("rr3_race_laps.py", "race-laps", [])]
VARIANTS += [("rr3_wtt.py", f"wtt-v{v}", ["--version", v]) for v in ("1", "2")]
VARIANTS += [("rr3_no_gplay.py", p, ["--parts", p]) for p in ("ui", "fblogout")]
VARIANTS += [("rr3_comp_ghost.py", "comp-ghost", [])]
VARIANTS += [("rr3_lb_tab.py", "lb-global", [])]
VARIANTS += [("rr3_skip_tutorial.py", "skip-tutorial", [])]
VARIANTS += [("rr3_selector_p2p.py", f"selector-p2p-v{v}", ["--version", v]) for v in ("1", "2")]
VARIANTS += [("rr3_browser_links.py", "browser-rr3-v1", [])]
VARIANTS += [("rr3_community.py", f"community-v{v}", ["--version", v]) for v in ("1", "2")]
# Needs rr3_debug_menu.py settings v5 (the PRR|Offline flag) first (#309).
VARIANTS += [("rr3_offline.py", "offline", [], ("rr3_debug_menu.py", ["--parts", "nosales,settings"]))]
# Highest allowed value (1000) so every byte the option can change shows up (#601).
VARIANTS += [("rr3_vinyl_limit.py", "vinyl-limit", ["--limit", "1000"])]
VARIANTS += [("rr3_wtt_winner_popup.py", f"wtt-winner-{p}", ["--parts", p]) for p in ("link", "hide")]
# Patch tools in VARIANTS order; rr3_build.py `patches` asks each of them.
PATCH_TOOLS = list(dict.fromkeys(v[0][:-3] for v in VARIANTS))

# Hand patches with no tool yet, and develified-owned sites: (tool, patch, start, end).
HAND = [
    # Offline progression gate (FUN_01516554 in Ghidra): `mov w0,#1; ret`, already
    # in develified; listed so no tool overlaps it (#336, docs/offline-progress.md).
    ("develified", "offline-progress", 0x1416554, 0x141655c),
    # lts-all (b08) rows retired 2026-11-04 (#320): replaced by rr3_wtt.py v2.
]


def ranges(a, b):
    out, i, n = [], 0, min(len(a), len(b))
    while i < n:
        if a[i] != b[i]:
            j = i
            while j < n and a[j] != b[j]:
                j += 1
            i, j = i & ~3, (j + 3) & ~3
            if out and i - out[-1][1] < GAP:
                out[-1][1] = j
            else:
                out.append([i, j])
            i = j
        else:
            i += 1
    return out


def generate():
    develified = gzip.open(DEVELIFIED).read()
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        inp = os.path.join(tmp, "develified.so")
        open(inp, "wb").write(develified)
        out = os.path.join(tmp, "out.so")
        first = os.path.join(tmp, "first.so")

        def patch(tool, name, src, dst, args):
            r = subprocess.run([sys.executable, os.path.join(HERE, tool), "patch", src, dst] + args,
                               capture_output=True, text=True)
            if r.returncode:
                raise SystemExit(f"{tool} {name} failed:\n{r.stdout}{r.stderr}")
            return open(dst, "rb").read()

        for tool, name, args, *pre in VARIANTS:
            base, src = develified, inp
            if pre:
                ptool, pargs = pre[0] if isinstance(pre[0], tuple) else (tool, pre[0])
                base, src = patch(ptool, name, inp, first, pargs), first
            d = patch(tool, name, src, out, args)
            if len(d) != len(develified):
                raise SystemExit(f"{tool} {name} changed the file size")
            for s, e in ranges(base, d):
                rows.append({"tool": tool, "patch": name, "start": f"0x{s:x}", "end": f"0x{e:x}",
                             "bytes": e - s})
    for tool, name, s, e in HAND:
        rows.append({"tool": tool, "patch": name, "start": f"0x{s:x}", "end": f"0x{e:x}", "bytes": e - s})
    return rows


def read_table():
    with open(TABLE, newline="") as f:
        return list(csv.DictReader(f))


def overlaps(rows):
    iv = sorted((int(r["start"], 16), int(r["end"], 16), r["tool"], r["patch"]) for r in rows)
    bad = []
    for i, (s, e, t, p) in enumerate(iv):
        for s2, e2, t2, p2 in iv[i + 1:]:
            if s2 >= e:
                break
            if t2 != t:
                bad.append(f"0x{max(s, s2):x}-0x{min(e, e2):x}: {t} {p} / {t2} {p2}")
    return bad


def read_caves(path=CAVES):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def span(r):
    return int(r["start"], 16), int(r["end"], 16)


def cave_use(cave, rows):
    """(rows that write in the cave, free (start, end) ranges left in it)."""
    s, e = span(cave)
    used = sorted((r for r in rows if span(r)[0] < e and s < span(r)[1]), key=span)
    free, at = [], s
    for r in used:
        a, b = span(r)
        if a > at:
            free.append((at, a))
        at = max(at, b)
    if at < e:
        free.append((at, e))
    return used, free


def sections(d):
    """{name: (start, end)} of an ELF64 file (file offsets)."""
    shoff, = struct.unpack_from("<Q", d, 0x28)
    size, num, strndx = struct.unpack_from("<HHH", d, 0x3A)
    sh = [struct.unpack_from("<IIQQQQ", d, shoff + i * size) for i in range(num)]
    names = sh[strndx][4]
    return {d[names + n:d.index(b"\0", names + n)].decode(): (off, off + sz) for n, _, _, _, off, sz in sh}


def cave_errors(caves, develified):
    """Rows of lib-code-caves.csv that don't match the develified lib."""
    bad, secs = [], sections(develified)
    for c in caves:
        s, e = span(c)
        name = f"cave {c['start']}-{c['end']}"
        if sorted(c) != sorted(CAVE_FIELDS):
            bad.append(f"{name}: columns are not {','.join(CAVE_FIELDS)}")
            continue
        if int(c["size"]) != e - s or e <= s:
            bad.append(f"{name}: size {c['size']} is not end - start")
        if c["kind"] not in SECTION:
            bad.append(f"{name}: kind {c['kind']!r} is not code or data")
            continue
        a, b = secs[SECTION[c["kind"]]]
        if not a <= s < e <= b:
            bad.append(f"{name}: not inside {SECTION[c['kind']]} (a {c['kind']} cave)")
        if c["kind"] == "code" and (s | e) & 3:
            bad.append(f"{name}: a code cave starts and ends on whole 4-byte words")
        if hashlib.sha256(develified[s:e]).hexdigest() != c["develified_sha256"]:
            bad.append(f"{name}: develified bytes differ from develified_sha256 (wrong range?)")
    iv = sorted(span(c) for c in caves)
    for (s, e), (s2, e2) in zip(iv, iv[1:]):
        if s2 < e:
            bad.append(f"caves 0x{s:x}-0x{e:x} and 0x{s2:x}-0x{e2:x} overlap")
    return bad


def requires_errors(rows, caves, declared):
    """Tools that write in a cave without declaring what it requires.
    declared: {tool: its REQUIRES}."""
    bad = set()
    for c in caves:
        need = [x.strip() for x in c["requires"].split(";") if x.strip()]
        for r in cave_use(c, rows)[0]:
            for x in need:
                if x not in declared.get(r["tool"], ()):
                    bad.add(f"{r['tool']} {r['patch']} writes in cave {c['start']}-{c['end']}, "
                            f"which requires {x}: add it to REQUIRES in {r['tool']}")
    return sorted(bad)


def tool_requires():
    """{tool: REQUIRES} of every patch tool (a cave it writes in may need them)."""
    sys.path.insert(0, HERE)
    return {t + ".py": list(getattr(importlib.import_module(t), "REQUIRES", [])) for t in PATCH_TOOLS}


def unlisted_tools():
    """Patch tools (a `def contents(` in tools/*.py) missing from VARIANTS."""
    out = []
    for f in sorted(os.listdir(HERE)):
        if f.endswith(".py") and f[:-3] not in PATCH_TOOLS:
            with open(os.path.join(HERE, f), encoding="utf-8") as fh:
                if re.search(r"^def contents\(", fh.read(), re.M):
                    out.append(f)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("update")
    sub.add_parser("check")
    f = sub.add_parser("find")
    f.add_argument("start")
    f.add_argument("end", nargs="?")
    c = sub.add_parser("caves")
    c.add_argument("--kind", choices=sorted(SECTION), help="only caves of this kind")
    a = ap.parse_args()

    if a.cmd == "caves":
        rows = read_table()
        for cave in read_caves():
            if a.kind and cave["kind"] != a.kind:
                continue
            used, free = cave_use(cave, rows)
            req = f", requires {cave['requires']}" if cave["requires"] else ""
            print(f"{cave['start']}-{cave['end']} {cave['kind']} {cave['size']} bytes{req}: {cave['what']}")
            for r in used:
                print(f"  used {r['start']}-{r['end']}  {r['tool']} {r['patch']}")
            for s, e in free:
                print(f"  free 0x{s:x}-0x{e:x}  {e - s} bytes")
            print(f"  {sum(e - s for s, e in free)} bytes free")
        return

    if a.cmd == "find":
        s = int(a.start, 16)
        e = int(a.end, 16) if a.end else s + 4
        hits = [r for r in read_table() if int(r["start"], 16) < e and s < int(r["end"], 16)]
        for r in hits:
            print(f"{r['start']}-{r['end']}  {r['tool']} {r['patch']}")
        print("free" if not hits else f"{len(hits)} range(s) already used")
        return

    rows = generate()
    bad = overlaps(rows)
    if a.cmd == "update":
        with open(TABLE, "w", newline="") as fh:
            w = csv.DictWriter(fh, FIELDS, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {len(rows)} ranges to {os.path.relpath(TABLE, ROOT)}")
    else:
        old = read_table()
        key = lambda r: tuple(str(r[k]) for k in FIELDS)  # noqa: E731
        if sorted(map(key, old)) != sorted(map(key, rows)):
            for r in sorted(set(map(key, rows)) - set(map(key, old))):
                print("missing from table:", " ".join(r))
            for r in sorted(set(map(key, old)) - set(map(key, rows))):
                print("not written by any tool:", " ".join(r))
            bad.append("table out of date: run rr3_patch_sites.py update")
        for f in unlisted_tools():
            bad.append(f"tool not listed: add {f} to VARIANTS in rr3_patch_sites.py")
        caves = read_caves()
        bad += ["caves table: " + b for b in cave_errors(caves, gzip.open(DEVELIFIED).read())]
        bad += ["tool requires: " + b for b in requires_errors(rows, caves, tool_requires())]
    for b in bad:
        print("ERROR" if b.startswith(("table", "tool", "caves")) else "OVERLAP", b)
    if bad:
        raise SystemExit(1)
    print("ok: no overlaps between tools" + ("; table up to date; caves table matches develified, cave "
                                             "requirements declared" if a.cmd == "check" else ""))


if __name__ == "__main__":
    main()
