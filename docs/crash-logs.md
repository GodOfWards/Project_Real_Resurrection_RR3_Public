# Crash logs (summary)

How to save the crash log when the game closes unexpectedly. Detailed
version (reading the log, which patch is at fault):
[details/crash-logs-details.md](details/crash-logs-details.md) (every detailed doc is in [`details/`](details/)).

Based on the latest `develified.apk` from the
[Project Real Resurrection Discord](https://discord.com/invite/project-resurrection-official-server-1482888689854971997)
(Mali GPU variant).

> **Project Real Resurrection.** Part of Project Real Resurrection's work on Real
> Racing 3. Not affiliated with, endorsed or supported by Electronic Arts.

## Steps (Shizuku + Termux, no root)

1. Start Shizuku and open `rish` in Termux (first time, or for one-line
   commands: [rish-guide.md](rish-guide.md#part-3-save-a-crash-log)).
2. After the crash (before rebooting the phone), run:
   ```sh
   logcat -b crash -d > /sdcard/Download/rr3-crash.txt
   exit
   ```
3. Share `Download/rr3-crash.txt`.

## Empty crash log

If `rr3-crash.txt` has nothing from RR3 at the time the game closed, it
wasn't a native crash: Android killed the game (usually out of memory) or
the game closed itself. Record the log while playing instead (in `rish`,
before opening the game; keep Termux awake with "Acquire wakelock"):

```sh
logcat -c
logcat -b main,system,events,crash -v time > /sdcard/Download/rr3-live.txt &
```

Reproduce the close, go back to `rish`, then:

```sh
kill %1
gzip -k /sdcard/Download/rr3-live.txt
```

Share `Download/rr3-live.txt.gz`.

## Game closes after every race

Reported by another player (Samsung Galaxy A14 5G, Exynos, Mali, 2026-10-14):
the game closes when a race is finished or quit instead of returning to the
menu. Build: our v0.3.0 (`b06`), which Tom has used without this problem.
Its patches don't run when a normal race ends (Time Trial laps only runs in
Time Trial; store and drive cost run in menus), so a patch is unlikely.
Switching to our build needs an uninstall, reinstall and a restore of
`files/` by hand, which makes the restored data the main suspect. Not solved
yet. At the end of a race the game writes the save
(`files/doc/character.2.dat`) and leaves the track, so check, in order:

1. Which APK/build is installed (stock `develified.apk` or a patched build:
   [builds.md](builds.md)).
2. Free storage space (a failed save write is a likely trigger).
3. Whether the save in `files/doc` was replaced or restored by hand; try
   the game once with its own fresh save.
4. Capture `rr3-crash.txt` right after it closes; if empty, the live log
   above.

---

Detailed version: [details/crash-logs-details.md](details/crash-logs-details.md). Every detailed doc is in
[`details/`](details/).
