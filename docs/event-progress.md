# Reset event progress (summary)

Reset single events, whole series or tiers, or everything except chosen
series, so they can be raced again from 0 % with the "new" badge. Save edit
only. Confirmed in game. Detailed version:
[details/event-progress-details.md](details/event-progress-details.md) (every detailed doc is in [`details/`](details/)).

Based on the latest `develified.apk` from the
[Project Real Resurrection Discord](https://discord.com/invite/project-resurrection-official-server-1482888689854971997)
(Mali GPU variant).

> **Project Real Resurrection.** Part of Project Real Resurrection's work on Real
> Racing 3. Not affiliated with, endorsed or supported by Electronic Arts.

## Steps

1. Copy `files/doc/character.2.dat` off the phone (game closed); keep the
   original. See [save-file.md](save-file.md).
2. Find what to reset:
   ```sh
   python3 tools/rr3_events.py list character.2.dat --recent 10   # last played events
   python3 tools/rr3_events.py series character.2.dat             # played events per series
   grep -i "le mans" tables/event-index.csv                         # any event or series
   ```
3. Reset into a new file, one of:
   ```sh
   python3 tools/rr3_events.py reset character.2.dat out.dat --event 34325
   python3 tools/rr3_events.py reset character.2.dat out.dat --series 507
   python3 tools/rr3_events.py reset character.2.dat out.dat --tier 103645
   python3 tools/rr3_events.py reset character.2.dat out.dat --all --keep-series 732
   ```
4. Rename `out.dat` to `character.2.dat`, put it back in `files/doc/`,
   start the game.

Series stay unlocked; only results and completion are cleared.

---

Detailed version: [details/event-progress-details.md](details/event-progress-details.md). Every detailed doc is in
[`details/`](details/).
