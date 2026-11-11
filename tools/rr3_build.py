#!/usr/bin/env python3
"""Tell which patched build a libRealRacing3.so is, and keep the build table.

Every library build (develified, test or confirmed) has a number (b00, b01, ...)
and a row in tables/builds.csv, keyed by the md5 of the uncompressed
libRealRacing3.so. Builds of the main line also have a Project Real Resurrection
patch version (0.5.0, 0.5.1-test1, ...); the game's own version (RR3 14.0.1)
is not changed. The md5 of an APK is not used: signing and zipping change
it even when the library is the same.

  rr3_build.py id FILE...        FILE = .so, .so.gz or .apk
  rr3_build.py id --installed    the APK installed on this phone (Termux)
  rr3_build.py list
  rr3_build.py patches FILE      what a library contains, read from its bytes
  rr3_build.py add LIB --name NAME --base bNN [--version V]
                   [--status ...] [--pr N] [--file PATH] [--notes TEXT]

`patches` asks every patch tool what it finds in the library (its
`contents()`) and prints the `patches` column, e.g. "tt-laps=best@v2; store;
free-drives". Only revisions carry a version (`@v2`); a first version has
none. Bytes that differ from the develified library but no tool recognises are
reported, never guessed. `add` gives the library the next free number and
appends its row with that column (--patches only to override); a library
already in the table is refused. Guide: docs/builds.md.
"""
import argparse
import csv
import datetime
import gzip
import hashlib
import os
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TABLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tables', 'builds.csv')
FIELDS = ['build', 'version', 'lib_md5', 'name', 'base', 'patches', 'status', 'date', 'pull_request', 'file', 'notes']
APK_LIB = 'lib/arm64-v8a/libRealRacing3.so'
PACKAGE = 'com.ea.games.r3_row'
STATUSES = ['develified', 'untested', 'confirmed', 'failed']
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
DEVELIFIED = os.path.join(ROOT, 'game', 'develified-libRealRacing3.so.gz')
SITES = os.path.join(ROOT, 'tables', 'lib-patch-sites.csv')
# Patch tools in the order their entries are written: the one list in
# rr3_patch_sites.py, whose `check` fails when a tool is missing from it.
from rr3_patch_sites import PATCH_TOOLS  # noqa: E402


def load_table():
    with open(TABLE, newline='') as f:
        return list(csv.DictReader(f))


def open_lib(path):
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            if APK_LIB not in z.namelist():
                sys.exit(f'{path}: no {APK_LIB} in this APK')
            f = z.open(APK_LIB)
    elif path.endswith('.gz'):
        f = gzip.open(path, 'rb')
    else:
        f = open(path, 'rb')
    return f


def lib_md5(path):
    h = hashlib.md5()
    with open_lib(path) as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def lib_patches(path):
    """The `patches` column for a library, from its bytes."""
    import importlib
    with open_lib(path) as f:
        d = bytearray(f.read())
    out, bad = [], []
    for name in PATCH_TOOLS:
        mod = importlib.import_module(name)
        c = mod.contents(d)
        if c is None:
            bad.append(f'{name}.py: unrecognised bytes')
        elif c:
            out.append(c)
        # Combinations that would break the game (e.g. a part another needs).
        bad += [f'{name}.py: {p}' for p in getattr(mod, 'problems', lambda _: [])(d)]
    # Changes outside every tool's sites: a hand patch, or a tool not listed.
    with gzip.open(DEVELIFIED) as f:
        develified = f.read()
    with open(SITES, newline='') as f:
        sites = [(int(r['start'], 16), int(r['end'], 16), r) for r in csv.DictReader(f)]
    known = [(s, e) for s, e, r in sites if r['tool'] != 'hand']
    hand = [(s, e, r['patch']) for s, e, r in sites if r['tool'] == 'hand']
    if len(d) != len(develified):
        bad.append('file size differs from the develified library')
    else:
        other, B = set(), 1 << 16
        for blk in range(0, len(d), B):
            if d[blk:blk + B] == develified[blk:blk + B]:
                continue
            for i in range(blk, min(blk + B, len(d))):
                if d[i] == develified[i] or any(s <= i < e for s, e in known):
                    continue
                names = [p for s, e, p in hand if s <= i < e]
                if names:
                    other.update(names)
                elif len(bad) < 20:
                    bad.append(f'unknown change at {i:#x}')
        out += sorted(other)
    return '; '.join(out) or 'none', bad


def installed_apk():
    # Plain `pm path` from Termux can't see other apps on newer Android;
    # fall back to Shizuku's rish (~/rish), as in docs/details/builds-details.md.
    rish = os.path.expanduser('~/rish')
    for cmd in (['pm', 'path', PACKAGE], [rish, '-c', f'pm path {PACKAGE}']):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL).stdout
        except OSError:
            continue
        for line in out.splitlines():
            line = line.strip()
            if line.startswith('package:') and line.endswith('base.apk'):
                return line[len('package:'):]
    sys.exit(f'could not find the installed {PACKAGE} with "pm path" or ~/rish; '
             f'see docs/builds.md for the manual way')


def file_name(row):
    if row['version']:
        return f"libRealRacing3-v{row['version']}-{row['build']}.so.gz"
    return f"libRealRacing3-{row['build']}-{row['name']}.so.gz"


def show(row):
    ver = f"Project Real Resurrection v{row['version']}, " if row['version'] else ''
    print(f"  {ver}build {row['build']}  {row['name']}  ({row['status']}"
          + (f", {row['date']}" if row['date'] else '')
          + (f", pull request #{row['pull_request']}" if row['pull_request'] else '') + ')')
    print(f"  patches: {row['patches']}")
    if row['notes']:
        print(f"  notes:   {row['notes']}")


def cmd_id(args):
    rows = {r['lib_md5']: r for r in load_table()}
    paths = args.files + ([installed_apk()] if args.installed else [])
    if not paths:
        sys.exit('give a file or --installed')
    unknown = False
    for p in paths:
        md5 = lib_md5(p)
        print(f'{p}\n  lib md5 {md5}')
        if md5 in rows:
            show(rows[md5])
        else:
            print('  not in tables/builds.csv (unknown build)')
            unknown = True
    return 1 if unknown else 0


def cmd_patches(args):
    ok = True
    for p in args.files:
        pat, bad = lib_patches(p)
        print(f'{p}\n  patches: {pat}')
        for b in bad:
            print(f'  WARNING: {b}')
        ok = ok and not bad
    return 0 if ok else 1


def cmd_list(args):
    for r in load_table():
        print(f"{r['build']}  {r['version'] or '-':<20} {r['status']:<9}  {r['date'] or '-':<10}  {r['lib_md5']}  {r['name']}")
    return 0


def cmd_add(args):
    rows = load_table()
    md5 = lib_md5(args.lib)
    for r in rows:
        if r['lib_md5'] == md5:
            sys.exit(f"already in the table as {r['build']} ({r['name']})")
    if args.base not in {r['build'] for r in rows}:
        sys.exit(f'unknown base build {args.base}')
    if args.version and args.version in {r['version'] for r in rows}:
        sys.exit(f'version {args.version} is already used')
    patches = args.patches
    if not patches:
        patches, bad = lib_patches(args.lib)
        if bad:
            sys.exit('can\'t tell what this library contains (give --patches):\n  ' + '\n  '.join(bad))
    num = max(int(r['build'][1:]) for r in rows) + 1
    row = dict(build=f'b{num:02d}', version=args.version or '', lib_md5=md5, name=args.name, base=args.base,
               patches=patches, status=args.status,
               date=args.date or datetime.date.today().isoformat(),
               pull_request=args.pr or '', file=args.file or '', notes=args.notes or '')
    with open(TABLE, 'a', newline='') as f:
        csv.DictWriter(f, FIELDS, lineterminator='\n').writerow(row)
    print(f"added {row['build']}")
    show(row)
    print(f"  name the file: {file_name(row)} (APK: rr3-v{row['version']}.apk)" if row['version']
          else f"  name the file: {file_name(row)}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('id', help='which build is this library or APK')
    p.add_argument('files', nargs='*')
    p.add_argument('--installed', action='store_true', help='check the installed game (Termux on the phone)')
    p.set_defaults(fn=cmd_id)
    p = sub.add_parser('patches', help='what a library contains, from its bytes')
    p.add_argument('files', nargs='+')
    p.set_defaults(fn=cmd_patches)
    p = sub.add_parser('list', help='all builds')
    p.set_defaults(fn=cmd_list)
    p = sub.add_parser('add', help='number a new build and add it to the table')
    p.add_argument('lib', help='.so, .so.gz or .apk')
    p.add_argument('--name', required=True, help='short name, e.g. debug-menu-race')
    p.add_argument('--base', required=True, help='build it was made from, e.g. b06')
    p.add_argument('--patches', help='override what `patches` reads from the library')
    p.add_argument('--version', help='Project Real Resurrection version, e.g. 0.6.0-test1 (side builds: leave out)')
    p.add_argument('--status', choices=STATUSES, default='untested')
    p.add_argument('--date', help='YYYY-MM-DD (default today)')
    p.add_argument('--pr', help='pull request number')
    p.add_argument('--file', help='where the library is kept')
    p.add_argument('--notes')
    p.set_defaults(fn=cmd_add)
    args = ap.parse_args()
    sys.exit(args.fn(args))


if __name__ == '__main__':
    main()
