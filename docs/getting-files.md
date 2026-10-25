# Getting the game files (summary)

Every mod here starts from files on your phone: the game library
`libRealRacing3.so`, the `.nct` game data, and your save `character.2.dat`.
Detailed version (Shizuku and root setup, every command, troubleshooting):
[details/getting-files-details.md](details/getting-files-details.md) (every detailed doc is in [`details/`](details/)).

Based on the latest `develified.apk` from the
[Project Real Resurrection Discord](https://discord.com/invite/project-resurrection-official-server-1482888689854971997)
(Mali GPU variant).

> **Project Real Resurrection.** Part of Project Real Resurrection's work on Real
> Racing 3. Not affiliated with, endorsed or supported by Electronic Arts.

## What to know

- The library is inside the APK. If you have the APK file, you need no
  special access.
- Android 11+ blocks apps from `Android/data`, where the save and game data
  are. Termux needs **Shizuku** (`rish`) or **root** (`su`) for those.
- `rish` can't see Termux's home folder; pass files through `Download`.

## Steps

1. Set up Termux once: `termux-setup-storage`, then
   `pkg install python unzip zip openssl-tool apksigner aapt`. If `pkg`
   fails with `NO_PUBKEY` / "repository is not signed", run
   `apt install termux-keyring` first, then retry.
2. **Library from the APK file** (no Shizuku or root):
   ```sh
   unzip -p ~/storage/downloads/develified.apk lib/arm64-v8a/libRealRacing3.so > stock-libRealRacing3.so
   md5sum stock-libRealRacing3.so    # stock Mali: 0e8cc145c5a8b5d9e8ee9a4cb9483793
   ```
3. **Library from the installed game** (Shizuku: `./rish -c`, root: `su -c`):
   ```sh
   ./rish -c 'cp "$(pm path com.ea.games.r3_row | head -n1 | cut -d: -f2)" /sdcard/Download/rr3-installed.apk'
   unzip -p ~/storage/downloads/rr3-installed.apk lib/arm64-v8a/libRealRacing3.so > stock-libRealRacing3.so
   ```
4. **Save** (game closed):
   ```sh
   ./rish -c 'cp /sdcard/Android/data/com.ea.games.r3_row/files/doc/character.2.dat /sdcard/Download/'
   ```
   Put an edited one back the same way, in the other direction.
   0-byte copy or `Permission denied` after a reinstall or restore: see
   [rish-guide.md](rish-guide.md).

Next: [patched-library.md](patched-library.md) for the library,
[save-file.md](save-file.md) for the save.

---

Detailed version: [details/getting-files-details.md](details/getting-files-details.md). Every detailed doc is in
[`details/`](details/).
