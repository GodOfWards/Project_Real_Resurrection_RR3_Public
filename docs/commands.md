# Command templates (summary)

Copy-paste commands for the things done over and over on the phone:
building an APK from a patched library, installing it, backing up and
swapping saves, checking the installed build, and saving crash logs. Fill in
the variables at the top of each template, then paste. Detailed version
(what every line does, what to check, what goes wrong):
[details/commands-details.md](details/commands-details.md) (every detailed
doc is in [`details/`](details/)).

> **Mali GPU variant only.** Based on the latest `develified.apk` from the
> [Project Real Resurrection Discord](https://discord.com/invite/project-resurrection-official-server-1482888689854971997).

> **Project Real Resurrection.** Part of Project Real Resurrection's work on
> Real Racing 3. Not affiliated with, endorsed or supported by Electronic
> Arts.

## Before you start

- Termux set up once as in [getting-files.md](getting-files.md):
  packages, `termux-setup-storage`, `rish` in `~`, this repo's `tools/` and
  `tables/` in `~/rr3`.
- Signing key `~/rr3-apk/key.pk8` + `cert.pem` from the first build
  ([installing.md](installing.md)). Always sign with the same key.
- **Paste `./rish` lines one at a time.** Lines pasted after a `rish`
  command can be swallowed as its input.
- Close the game (swipe it away) before touching the save.
- Variables only live in the current Termux session. After reopening
  Termux, set them again.

## 1. Build an APK from a patched library

Put the library (`libRealRacing3-v<version>-bNN.so.gz`) in Download, then:

```sh
VER=0.5.1-test1
BUILD=b12
```
```sh
LIB=libRealRacing3-v$VER-$BUILD.so.gz
APK=rr3-v$VER.apk
mkdir -p ~/rr3-apk/lib/arm64-v8a && cd ~/rr3-apk
gunzip -c ~/storage/downloads/$LIB > lib/arm64-v8a/libRealRacing3.so
python3 ~/rr3/tools/rr3_build.py id lib/arm64-v8a/libRealRacing3.so
cp ~/storage/downloads/develified.apk game.apk
python3 ~/rr3/tools/rr3_cleartext.py make .     # http
zip -d game.apk 'META-INF/*'
zip -0 game.apk lib/arm64-v8a/libRealRacing3.so
zip game.apk res/xml/network_security_config.xml res/xml/network_security_config_ad_tech.xml     # http
zipalign -p -f 4 game.apk aligned.apk
apksigner sign --key key.pk8 --cert cert.pem --out $APK aligned.apk
python3 ~/rr3/tools/rr3_build.py id $APK
cp $APK ~/storage/downloads/
```

Both `rr3_build.py id` lines must show the version and build you set.

**Builds that talk to an http server** (`rr3_cc_local.py` with any port
but 443, e.g. `cc-local=100.82.32.18:8080` in `tables/builds.csv`) also
need the two `rr3_cleartext.py` lines (marked `# http`): stock
develified.apk blocks plain http, and without them the game sends nothing
to the server (b32, 2026-10-21). Leave them out for builds with no server
address or an https one (port 443).

## 2. Install it

Back up the save first (template 3). Then open `rr3-v<version>.apk` in
Download and tap **Update**. Afterwards check it (template 6).

Coming from an APK signed with a different key (the original
`develified.apk`, someone else's build): see
[installing.md](installing.md), a one-time back up, uninstall, install,
restore (template 5).

## 3. Back up the save

```sh
STAMP=$(date +%Y%m%d-%H%M)
./rish -c "cp /sdcard/Android/data/com.ea.games.r3_row/files/doc/character.2.dat /sdcard/Download/character.2.dat.$STAMP"
```

Makes `Download/character.2.dat.<date-time>`. If the copy is 0 bytes or
says `Permission denied`, run template 4b, start the game once so it saves,
close it, and try again.

## 4. Put a save in place

### 4a. Copy the save

The save to use, in Download:

```sh
SAVE=character.2.dat
```
```sh
./rish -c "cp /sdcard/Download/$SAVE /sdcard/Android/data/com.ea.games.r3_row/files/doc/character.2.dat"
```

### 4b. Doc-folder fix

Run after anything that recreated `files/doc` (restoring `files`,
extracting the `files` zip, deleting folders with ZArchiver or rish).
Full guide, from installing Termux and rish to checking the folder:
[rish-guide.md](rish-guide.md).

```sh
./rish -c 'chgrp 1078 /sdcard/Android/data/com.ea.games.r3_row/files/doc && chmod 2770 /sdcard/Android/data/com.ea.games.r3_row/files/doc'
```

## 5. Back up and restore all game data

Back up (before uninstalling):

```sh
./rish -c 'cp -r /sdcard/Android/data/com.ea.games.r3_row /sdcard/Download/rr3-backup'
```

Restore (after installing, opening the game once and closing it). `rm -rf`
deletes the game's data folder, check the path:

```sh
./rish -c 'rm -rf /sdcard/Android/data/com.ea.games.r3_row/files && cp -r /sdcard/Download/rr3-backup/files /sdcard/Android/data/com.ea.games.r3_row/'
```

Then the doc-folder fix (4b).

## 6. Which build is installed?

```sh
python3 ~/rr3/tools/rr3_build.py id --installed
```

If `pm` doesn't work in plain Termux, use rish
([details](details/commands-details.md#6-which-build-is-installed)).

## 7. Re-sign someone else's APK (test builds)

The APK file in Download:

```sh
IN=test.apk
OUT=rr3-test-signed.apk
```
```sh
cd ~/rr3-apk
cp ~/storage/downloads/$IN test.apk
aapt dump badging test.apk | head -1
zip -d test.apk 'META-INF/*.SF' 'META-INF/*.RSA' 'META-INF/*.EC' 'META-INF/MANIFEST.MF'
zipalign -p -f 4 test.apk test-aligned.apk
apksigner sign --key key.pk8 --cert cert.pem --out ~/storage/downloads/$OUT test-aligned.apk
```

The `aapt` line must say `name='com.ea.games.r3_row'`. Then install with
**Update**.

## 8. Crash log

After the crash, before rebooting the phone:

```sh
./rish -c 'logcat -b crash -d > /sdcard/Download/rr3-crash.txt'
```

Share `Download/rr3-crash.txt` ([crash-logs.md](crash-logs.md)). Empty
log, or recording while playing: [rish-guide.md](rish-guide.md#part-3-save-a-crash-log).

## 9. Get the stock library

```sh
unzip -p ~/storage/downloads/develified.apk lib/arm64-v8a/libRealRacing3.so > ~/rr3/stock-libRealRacing3.so
md5sum ~/rr3/stock-libRealRacing3.so    # stock Mali: 0e8cc145c5a8b5d9e8ee9a4cb9483793
```

---

Detailed version: [details/commands-details.md](details/commands-details.md).
Every detailed doc is in [`details/`](details/).
