#!/usr/bin/env python3
"""Admin member move for rr3_cc_server.py (docs/member-move.md): give the
phone now known as member FROM (its new player key) the member id TO (its
old player key), merging FROM's data into TO. For a player whose phone got
a new player key (new Android id: an APK signed with another key, or a
lost phone) and who has proved they own TO (see docs/member-move.md).

Part of Project Real Resurrection's work on Real Racing 3. Not affiliated
with, endorsed or supported by Electronic Arts.

Run next to rr3_cc_server.py (its data/ folder) with the server STOPPED:
    python3 rr3_member_move.py 1025 1001            # dry run: prints what would change
    python3 rr3_member_move.py 1025 1001 --apply    # writes the files
    [--data DIR]  the server's data folder (default: data/ in the current folder)
    [--saves DIR] the cloud saves folder (--cloud-save-dir; default: DIR/saves)
    [--no-running-check]  skip the "server running" check (tests only)

After: the FROM phone's key holds member TO; TO's old key is retired; FROM's
id is left unused. Best times, ghosts: the faster one wins. Username: TO's
if it has one. Secret: the FROM phone's (current) one. Friends, mail,
shadowed: the old key replaced by the new one. Pending ghost uploads of
both keys are dropped. Prints counts only (no keys, no ids beyond the two).

Cloud saves (v1.1, #501/#530): TO's versions stay as they are, so the game
keeps offering TO's career (usually the one the player wants back after a
new phone key). FROM's versions (and corrupt reports) move into
saves/TO/moved-from-FROM/: kept, never offered or rotated; an admin can
bring one back with rr3_cloud_preset.py promote. pins.json: FROM's pin
dropped, TO's kept. site.json: TO's entry kept, opted in if either was,
both members' preset picks count; FROM's base and preset marks dropped
(their files moved). Open upload slots and restore keys of both dropped.
"""
import json, os, sys

# v1.0 (2026-11-03, first used for Tom's A32: 1025 -> 1001).
# v1.1 (2026-11-09, #530): cloud saves (data/saves) moved too.
VERSION = "1.1"
D = "data"


def load(path, default):
    try:
        return json.load(open(path))
    except FileNotFoundError:
        return default


def save(path, data, apply, mode=None):
    if not apply:
        return
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode or 0o644)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=1, sort_keys=True)
    if mode:
        os.chmod(tmp, mode)
    os.replace(tmp, path)


def main():
    global D
    argv = sys.argv[1:]
    if "--data" in argv:
        i = argv.index("--data")
        D = argv[i + 1]
        del argv[i:i + 2]
    saves_dir = None
    if "--saves" in argv:
        i = argv.index("--saves")
        saves_dir = argv[i + 1]
        del argv[i:i + 2]
    saves_dir = saves_dir or os.path.join(D, "saves")
    a = [x for x in argv if not x.startswith("--")]
    apply = "--apply" in argv
    check_running = "--no-running-check" not in argv
    if len(a) != 2 or not all(x.isdigit() for x in a):
        sys.exit(__doc__)
    src, dst = int(a[0]), int(a[1])
    mp = os.path.join(D, "rr3-members.json")
    m = load(mp, None)
    if m is None:
        sys.exit(f"no {mp}: run in the rr3 folder or give --data")
    by = {v: k for k, v in m["members"].items()}
    new, old = by.get(src), by.get(dst)
    if not new or not old:
        sys.exit(f"member {src if not new else dst} not found")
    if check_running and os.system('pgrep -f "rr3_cc_[s]erver.py" >/dev/null') == 0:
        sys.exit("rr3_cc_server.py is running: stop it first (it would overwrite these files)")
    target = os.path.join(saves_dir, str(dst), f"moved-from-{src}")
    if os.path.isdir(os.path.join(saves_dir, str(src))) and os.path.exists(target):
        sys.exit(f"{target} already exists: move it away by hand first (nothing written)")
    print(f"rr3_member_move.py v{VERSION} " + ("APPLY" if apply else "DRY RUN") + f": member {src} -> {dst}")

    # members
    del m["members"][old]
    m["members"][new] = dst
    save(mp, m, apply)
    print(f"members: key of {dst} retired, {src}'s key now {dst}; {src} unused")

    # best times
    tp = os.path.join(D, "rr3-leaderboard.json")
    t = load(tp, {})
    took_old = took_new = 0
    for ev in t.values():
        o, n = ev.pop(old, None), ev.get(new)
        if o is None:
            continue
        if n is None or o["time_ms"] <= n["time_ms"]:
            ev[new] = o
            took_old += 1
        else:
            took_new += 1
    save(tp, t, apply)
    print(f"times: {took_old} from {dst} kept, {took_new} events where {src} was faster")

    # usernames
    up = os.path.join(D, "rr3-usernames.json")
    u = load(up, {})
    if old in u:
        u[new] = u.pop(old)
    save(up, u, apply)
    print(f"username: {u.get(new)!r}")

    # mail
    lp = os.path.join(D, "rr3-mail.json")
    mail = load(lp, {})
    box = mail.pop(old, []) + mail.pop(new, [])
    if box:
        latest = {}
        for x in sorted(box, key=lambda x: -x["time"]):
            latest.setdefault(x["event"], x)
        mail[new] = sorted(latest.values(), key=lambda x: -x["time"])
    n_sender = 0
    for lst in mail.values():
        for x in lst:
            if x.get("sender") == old:
                x["sender"] = new
                n_sender += 1
    save(lp, mail, apply)
    print(f"mail: {len(mail.get(new, []))} in the box, {n_sender} sender(s) renamed")

    # friends
    fp = os.path.join(D, "rr3-friends.json")
    fr = load(fp, {"friends": [], "requests": []})
    sw = lambda k: new if k == old else k
    pairs = {}
    for x, y, ts in fr.get("friends", []):
        x, y = sw(x), sw(y)
        if x != y:
            p = tuple(sorted((x, y)))
            pairs[p] = min(ts, pairs.get(p, ts))
    reqs = {}
    for x, y, ts in fr.get("requests", []):
        x, y = sw(x), sw(y)
        if x != y and tuple(sorted((x, y))) not in pairs:
            reqs[(x, y)] = min(ts, reqs.get((x, y), ts))
    fr = dict(friends=sorted([*p, ts] for p, ts in pairs.items()),
              requests=sorted([x, y, ts] for (x, y), ts in reqs.items()))
    save(fp, fr, apply)
    print(f"friends: {sum(new in p for p in pairs)} friend(s), "
          f"{sum(new in r for r in reqs)} request(s) for the moved player")

    # secrets: keep the phone's current one
    sp = os.path.join(D, "rr3-secrets.json")
    s = load(sp, {})
    s.pop(old, None)
    save(sp, s, apply, 0o600)
    print(f"secret: current phone's kept ({'yes' if new in s else 'none stored yet'})")

    # shadowed
    hp = os.path.join(D, "rr3-shadowed.json")
    if os.path.exists(hp):
        h = load(hp, [])
        h2 = sorted({sw(k) for k in h})
        save(hp, h2, apply)
        print(f"shadowed: {'moved player listed' if new in h2 else 'not listed'}")

    # ghosts
    gd = os.path.join(D, "ghosts")
    gp = os.path.join(gd, "index.json")
    g = load(gp, {"slots": {}, "ghosts": {}})
    dropped = [k for k, v in g["slots"].items() if v.get("player") in (old, new)]
    for k in dropped:
        del g["slots"][k]
    moved = kept = 0
    for name in [x for x in g["ghosts"] if x.startswith(f"{src}_")]:
        ev = name.split("_", 1)[1]
        to = f"{dst}_{ev}"
        mine, theirs = g["ghosts"].pop(name), g["ghosts"].get(to)
        f_src, f_dst = os.path.join(gd, name + ".bin"), os.path.join(gd, to + ".bin")
        if theirs is None or mine["lap_ms"] <= theirs["lap_ms"]:
            g["ghosts"][to] = mine
            if apply and os.path.exists(f_src):
                os.replace(f_src, f_dst)
            moved += 1
        else:
            if apply and os.path.exists(f_src):
                os.remove(f_src)
            kept += 1
    if apply:
        for k in dropped:
            try:
                os.remove(os.path.join(gd, f"upload_{k}.bin"))
            except FileNotFoundError:
                pass
    save(gp, g, apply)
    print(f"ghosts: {moved} of {src}'s moved to {dst}, {kept} slower dropped, "
          f"{len(dropped)} pending upload(s) dropped")
    move_saves(saves_dir, src, dst, apply)
    print("done" if apply else "nothing written (add --apply)")


def move_saves(sd, src, dst, apply):
    """v1.1: cloud saves (rr3_cc_server.py CloudSaves). TO's versions stay
    offered; FROM's go to saves/TO/moved-from-FROM/ (kept, not offered)."""
    if not os.path.isdir(sd):
        print("cloud saves: none (no saves folder)")
        return
    s_src, s_dst = os.path.join(sd, str(src)), os.path.join(sd, str(dst))
    moved = 0
    if os.path.isdir(s_src):
        names = []
        for root, _dirs, files in os.walk(s_src):
            names += [os.path.relpath(os.path.join(root, n), s_src) for n in files if not n.startswith(".")]
        moved = len(names)
        if apply:
            target = os.path.join(s_dst, f"moved-from-{src}")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            os.replace(s_src, target)
    pp = os.path.join(sd, "pins.json")
    pins = load(pp, {})
    dropped_pin = pins.pop(str(src), None) is not None
    if os.path.exists(pp):
        save(pp, pins, apply)
    sp = os.path.join(sd, "site.json")
    site = load(sp, {"members": {}})
    ms = site.setdefault("members", {})
    a, b = ms.pop(str(src), None), ms.get(str(dst))
    if a is not None:
        b = ms.setdefault(str(dst), {})
        b["optin"] = bool(a.get("optin") or b.get("optin"))
        b["picks"] = sorted(set(a.get("picks", [])) | set(b.get("picks", [])))
    if os.path.exists(sp) or a is not None:
        save(sp, site, apply)
    kp = os.path.join(sd, "slots.json")
    keys = load(kp, {})
    n_keys = 0
    for part in ("slots", "restores"):
        for k in [k for k, v in keys.get(part, {}).items() if v.get("member") in (src, dst)]:
            del keys[part][k]
            n_keys += 1
    if os.path.exists(kp):
        save(kp, keys, apply)
    print(f"cloud saves: {dst}'s versions kept (offered); {moved} file(s) of {src} "
          f"{'moved' if apply else 'to move'} into {dst}/moved-from-{src}/ (kept, not offered); "
          f"{src}'s pin {'dropped' if dropped_pin else 'none'}; site state "
          f"{'merged' if a is not None else 'unchanged'}; {n_keys} open key(s) dropped")


if __name__ == "__main__":
    main()
