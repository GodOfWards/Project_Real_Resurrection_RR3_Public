# Save file (summary)

The career save `character.2.dat` holds currencies, cars and event progress.
Every save edit in this repo works on it. Detailed version:
[details/save-file-details.md](details/save-file-details.md) (every detailed doc is in [`details/`](details/)).

Based on the latest `develified.apk` from the
[Project Real Resurrection Discord](https://discord.com/invite/project-resurrection-official-server-1482888689854971997)
(Mali GPU variant).

> **Project Real Resurrection.** Part of Project Real Resurrection's work on Real
> Racing 3. Not affiliated with, endorsed or supported by Electronic Arts.

## What to know

- Location: `Android/data/com.ea.games.r3_row/files/doc/character.2.dat`.
- It is lightly encrypted and ends with a checksum byte. **A save with a
  wrong checksum is silently ignored**, so never edit it by hand; use the
  tools, which fix the checksum for you.
- The tools read the encrypted file directly and write a new encrypted file.
  The input is never changed.

## Steps

1. Close the game. Copy `files/doc/character.2.dat` off the phone and keep
   that original ([getting-files.md](getting-files.md) shows how).
2. Check it reads: `python3 tools/rr3_dat.py header character.2.dat`
   (should show magic `0xabcffcba`, version 5).
3. Edit with the tool for the feature:
   [wallet.md](wallet.md), [event-progress.md](event-progress.md),
   [cars-and-vip.md](cars-and-vip.md).
4. Rename the result to `character.2.dat`, copy it back into `files/doc/`,
   start the game.
5. If nothing changed in game, put the original back (the game rejected the
   file).

---

Detailed version: [details/save-file-details.md](details/save-file-details.md). Every detailed doc is in
[`details/`](details/).
