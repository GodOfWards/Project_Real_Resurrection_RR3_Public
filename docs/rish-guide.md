# Termux and rish for players: save copy fix, crash logs (summary)

A step-by-step guide for players, starting from nothing: set up Termux with
Shizuku (`rish`) once, then use it to fix save copies that come out as **0
bytes / `Permission denied`** after a reinstall, and to **save a crash log**
when the game closes. Detailed version (why, every step explained,
troubleshooting): [details/rish-guide-details.md](details/rish-guide-details.md)
(every detailed doc is in [`details/`](details/)). Issue
[#59](https://github.com/GodOfWards/Project-Real-Resurrection-RR3/issues/59).

> **Mali GPU variant only.** Based on the latest `develified.apk` from the
> [Project Real Resurrection Discord](https://discord.com/invite/project-resurrection-official-server-1482888689854971997).
> Nothing in this guide depends on the GPU variant.

> **Project Real Resurrection.** Part of Project Real Resurrection's work on
> Real Racing 3. Not affiliated with, endorsed or supported by Electronic
> Arts.

Paste **one line at a time**: lines pasted after a `./rish` command can be
swallowed.

## Part 1. Set up Termux and rish (once)

1. **Termux.** Install Termux (F-Droid or Play Store) and open it. Give it
   storage access and accept the prompt:
   ```sh
   termux-setup-storage
   ```
2. **Shizuku.** Install Shizuku and start it with **Start via Wireless
   debugging** (pair once with the code from Developer options). Redo the
   start after every reboot.
3. **Export rish.** In Shizuku: **Use Shizuku in terminal apps** →
   **Export files** → pick `Download`, make a folder `shizuku`, select it.
4. **Install rish in Termux:**
   ```sh
   cp ~/storage/downloads/shizuku/rish ~/storage/downloads/shizuku/rish_shizuku.dex ~/
   ```
   ```sh
   cd ~ && sed -i 's/PKG/com.termux/' rish && chmod 700 rish && chmod 400 rish_shizuku.dex
   ```
5. **Test rish.** Allow Termux if Shizuku asks.
   ```sh
   ./rish -c id
   ```
   Must start with `uid=2000(shell)`.

## Part 2. Save copies are 0 bytes / Permission denied

**Status:** confirmed on one phone (Tom's, 2026-10-12). Expected to work on
any Android 11+ phone (group `1078` is Android's standard group for app
data folders), not yet tested elsewhere.

**Why:** the game's data folder gives new files a group (`1078`) that
`rish` and file managers can read. Deleting and recreating `files/doc`
(restoring a backup, extracting the `files` zip, ZArchiver) loses that, so
every file the game saves afterwards is private to the game.

1. **Check.** Close the game (swipe it away), then:
   ```sh
   ./rish -c 'ls -ln /sdcard/Android/data/com.ea.games.r3_row/files'
   ```
   Look at the `doc` line. Group `1078` (fourth column) and `drwxrws`:
   folder is fine. `2000 2000`, or `drwx` without the `s`: you have this
   problem.
2. **Fix:**
   ```sh
   ./rish -c 'chgrp 1078 /sdcard/Android/data/com.ea.games.r3_row/files/doc && chmod 2770 /sdcard/Android/data/com.ea.games.r3_row/files/doc'
   ```
   No output means it worked. Run step 1 again: `doc` now shows
   `drwxrws---` and `1078`.
3. **Let the game save.** Files saved before the fix stay unreadable.
   Open the game, play a race, close it.
4. **Copy the save:**
   ```sh
   ./rish -c 'cp /sdcard/Android/data/com.ea.games.r3_row/files/doc/character.2.dat /sdcard/Download/'
   ```
   It should be about 4 MB in `Download`.

Repeat step 2 after anything that recreates `files/doc` again. Avoid
deleting or recreating folders under `files/` with rish or ZArchiver.

## Part 3. Save a crash log

1. **Right after the game closes** (any time before the phone reboots):
   ```sh
   ./rish -c 'logcat -b crash -d > /sdcard/Download/rr3-crash.txt'
   ```
2. **Check it has the game in it:**
   ```sh
   grep -c r3_row ~/storage/downloads/rr3-crash.txt
   ```
   More than `0`: share `Download/rr3-crash.txt`. `0` (or an empty file):
   it wasn't a native crash, go to step 3.
3. **Record a log while playing.** Turn on **Acquire wakelock** in
   Termux's notification, then:
   ```sh
   ./rish -c 'logcat -c'
   ```
   ```sh
   ./rish -c 'logcat -b main,system,events,crash -v time -f /sdcard/Download/rr3-live.txt'
   ```
   Leave Termux running, switch to the game, make it close again. Go back
   to Termux, stop recording with **Ctrl+C** (Termux's extra-keys row:
   `CTRL`, then `c`), and pack it:
   ```sh
   gzip -kf ~/storage/downloads/rr3-live.txt
   ```
   Share `Download/rr3-live.txt.gz`.

Reading the log and known crash causes: [crash-logs.md](crash-logs.md).

---

Detailed version: [details/rish-guide-details.md](details/rish-guide-details.md).
Every detailed doc is in [`details/`](details/).
