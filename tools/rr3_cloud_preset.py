#!/usr/bin/env python3
"""Put a preset character.2.dat into a member's cloud saves, for a test on
one phone (issue #530, cloud save phase (c); analysis/cloud-save.md 2.6, 9).

A cloud save upload is a BinaryBlob mode 1 of a small bundle: u32 2, u32 3,
then character.2.dat, player_profile.2.dat and nrc.bin.2.dat (name, size,
bytes). This tool builds that bundle from a preset character.2.dat (used
as-is, Tom 2026-11-09) and the other two files, checks it exactly as CC
does before offering a save (rr3_cc_server.save_check, v5.70), and stores
it as the member's newest version. The game's Cloud Save screen then offers
it ("Restore To Device").

The other two files come from the member's own newest upload (--from-newest,
the default), from a given upload (--from FILE), or from loose files
(--profile, --nrc).

Run on the box as the user CC runs as, from the folder that holds
rr3_cc_server.py and rr3_cc_blob.py (or the repo's tools/). CC keeps
running: it reads the folder on every 47. Only members in
--cloud-save-restore see the row.

Usage:
  rr3_cloud_preset.py check FILE                       (an upload: does CC accept it?)
  rr3_cloud_preset.py show FILE                        (the three files inside, sizes, md5s)
  rr3_cloud_preset.py build PRESET OUT [--from FILE | --profile F --nrc F]
  rr3_cloud_preset.py install PRESET --member N [--saves-dir DIR]
                      [--from-newest | --from FILE | --profile F --nrc F] [--dry-run]
  rr3_cloud_preset.py promote FILE --member N [--saves-dir DIR] [--dry-run]
                      (store an earlier upload again as the newest version: going back)

PRESET is a character.2.dat (encrypted, as the game writes it). FILE is a
stored upload (data/saves/<member>/<UTC>-<md5>.bin).

Part of Project Real Resurrection's work on Real Racing 3. Not affiliated
with, endorsed or supported by Electronic Arts.
"""
# v1 (2026-11-09, #530): check, show, build, install, promote.
VERSION = "1"

import argparse
import hashlib
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rr3_cc_blob as blob  # noqa: E402
import rr3_cc_server as server  # noqa: E402

DEFAULT_SAVES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "saves")


def unbundle(body):
    """The three files of an upload, {name: bytes}. Raises ValueError."""
    if len(body) < 12:
        raise ValueError("too short")
    _chk, mode, size = struct.unpack_from("<III", body)
    if mode != 1:
        raise ValueError(f"blob mode {mode}")
    plain = zlib.decompress(body[12:])
    if len(plain) != size:
        raise ValueError(f"unpacks to {len(plain)} bytes, {size} declared")
    ver, count = struct.unpack_from("<II", plain)
    if ver != 2:
        raise ValueError(f"bundle version {ver}")
    i, files = 8, {}
    for _ in range(count):
        name, i = server.read_string(plain, i)
        n = struct.unpack_from("<I", plain, i)[0]
        files[name], i = plain[i + 4:i + 4 + n], i + 4 + n
    return files


def bundle(character, profile, nrc):
    """BinaryBlob mode 1 of u32 2, u32 3 + the three files, in the game's order."""
    files = (("character.2.dat", character), ("player_profile.2.dat", profile), ("nrc.bin.2.dat", nrc))
    plain = blob.u32(2, len(files)) + b"".join(blob.string(n) + blob.u32(len(d)) + d for n, d in files)
    return blob.wrap(plain, 1)


def name_for(body):
    """A name as CC stores it, for save_check (the time part doesn't matter there)."""
    return f"20000101T000000000000Z-{hashlib.md5(body).hexdigest()}.bin"


def check(body):
    """None if CC v5.70+ would offer and send this upload, else why not."""
    return server.save_check(body, name_for(body))


def read(path):
    with open(path, "rb") as f:
        return f.read()


def others(a, saves):
    """(player_profile.2.dat, nrc.bin.2.dat) for build/install, from the options."""
    if a.profile or a.nrc:
        if not (a.profile and a.nrc):
            sys.exit("--profile and --nrc go together")
        return read(a.profile), read(a.nrc), f"{a.profile}, {a.nrc}"
    src = a.source
    if src is None:
        if a.member is None:
            sys.exit("give --from FILE, or --profile and --nrc")
        names = saves.stored(saves.member_dir(a.member))
        good = [n for n in reversed(names) if saves.checked(saves.member_dir(a.member), n) is None]
        if not good:
            sys.exit(f"member {a.member} has no upload that passes the checks: tap Backup To Cloud once, "
                     "or give --from / --profile --nrc")
        src = os.path.join(saves.member_dir(a.member), good[0])
    files = unbundle(read(src))
    return files["player_profile.2.dat"], files["nrc.bin.2.dat"], src


def store(saves, member, body, dry_run):
    why = check(body)
    if why:
        sys.exit(f"refused: {why} (CC would never offer it)")
    if dry_run:
        print(f"dry run: would store {len(body)} bytes md5 {hashlib.md5(body).hexdigest()} for member {member}")
        return
    with saves.lock:
        new, md5, kept = saves.store(member, body)
    newest = saves.stored(saves.member_dir(member))[-1]
    print(f"member {member}: {len(body)} bytes md5 {md5}: " + ("stored" if new else "same as newest, not stored again")
          + f" as {newest}; {kept} rolling version(s); pinned: {saves.pinned(member) or 'none'}")
    print("In game: Settings > Cloud Save shows it as the newest; Restore To Device loads it.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("check", "show"):
        p = sub.add_parser(c)
        p.add_argument("file")
    for c in ("build", "install"):
        p = sub.add_parser(c)
        p.add_argument("preset")
        if c == "build":
            p.add_argument("out")
        p.add_argument("--from", dest="source", metavar="FILE", help="take the other two files from this upload")
        p.add_argument("--profile", metavar="FILE", help="player_profile.2.dat")
        p.add_argument("--nrc", metavar="FILE", help="nrc.bin.2.dat")
        p.add_argument("--member", type=int, help=None if c == "install" else argparse.SUPPRESS,
                       required=c == "install")
        p.add_argument("--saves-dir", default=DEFAULT_SAVES)
        p.add_argument("--from-newest", action="store_true",
                       help="the other two files from the member's newest good upload (default)")
        p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("promote")
    p.add_argument("file")
    p.add_argument("--member", type=int, required=True)
    p.add_argument("--saves-dir", default=DEFAULT_SAVES)
    p.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    if a.cmd == "check":
        why = check(read(a.file))
        print("ok: CC would offer and send it" if why is None else f"refused: {why}")
        return 0 if why is None else 1
    if a.cmd == "show":
        body = read(a.file)
        print(f"{a.file}: {len(body)} bytes md5 {hashlib.md5(body).hexdigest()}")
        for n, d in unbundle(body).items():
            print(f"  {n:22} {len(d):>9} bytes md5 {hashlib.md5(d).hexdigest()}")
        why = check(body)
        print("  check: ok" if why is None else f"  check: refused: {why}")
        return 0
    if a.cmd == "promote":
        saves = server.CloudSaves(a.saves_dir, None)
        store(saves, a.member, read(a.file), a.dry_run)
        return 0
    preset = read(a.preset)
    why = server.dat_check(preset)
    if why:
        sys.exit(f"{a.preset}: not a character.2.dat the game accepts: {why}")
    saves = server.CloudSaves(a.saves_dir, None) if a.cmd == "install" else None
    profile, nrc, src = others(a, saves)
    body = bundle(preset, profile, nrc)
    print(f"preset {a.preset} ({len(preset)} bytes) + player_profile/nrc from {src}")
    if a.cmd == "build":
        why = check(body)
        with open(a.out, "wb") as f:
            f.write(body)
        print(f"wrote {a.out}: {len(body)} bytes md5 {hashlib.md5(body).hexdigest()}; check: "
              + ("ok" if why is None else f"refused: {why}"))
        return 0 if why is None else 1
    store(saves, a.member, body, a.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
