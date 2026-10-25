# Combined patched library (summary)

One `libRealRacing3.so` with every confirmed library patch: Time Trial laps
(`best`), store purchases, and no drive point cost. This is the current
build, confirmed in game. Detailed version (every step, every changed byte):
[details/patched-library-details.md](details/patched-library-details.md) (every detailed doc is in [`details/`](details/)).

> **Mali GPU variant only.** Based on the latest `develified.apk` from the
> [Project Real Resurrection Discord](https://discord.com/invite/project-resurrection-official-server-1482888689854971997).
> Each tool refuses a library it doesn't recognise.

> **Project Real Resurrection.** Part of Project Real Resurrection's work on Real
> Racing 3. Not affiliated with, endorsed or supported by Electronic Arts.

## Steps

1. Get the stock library from your APK or installed game as
   `stock-libRealRacing3.so` ([getting-files.md](getting-files.md)), then
   build (Python 3, in Termux or on a computer):
   ```sh
   python3 tools/rr3_tt_laps.py patch stock-libRealRacing3.so step1.so --laps best --best-version 3
   python3 tools/rr3_mtx.py patch step1.so step2.so
   python3 tools/rr3_drive_cost.py patch step2.so libRealRacing3.so
   ```
   (This is build `b11`; the repo no longer keeps ready-made builds, see
   [game/README.md](../game/README.md).)
2. Check: `md5sum libRealRacing3.so` must be
   `5a14c7a19607f257b64eb6f4bca0ed52` (laps `best` v3; the earlier v2 build
   was `08a93af7fac3497a3a2a5c457d2e5ab5`). Without `--best-version 3` the
   tool writes the latest, v4, and the md5 differs.
3. Put it in the APK, sign and install: [installing.md](installing.md).

Features: [time-trial-laps.md](time-trial-laps.md),
[store-purchases.md](store-purchases.md),
[time-trial-drive-points.md](time-trial-drive-points.md).

---

Detailed version: [details/patched-library-details.md](details/patched-library-details.md). Every detailed doc is in
[`details/`](details/).
