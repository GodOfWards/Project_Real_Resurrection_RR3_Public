# Currency balances (summary)

Set your Gold, R$ and M$ balances in the save. No APK change. Confirmed in
game. Detailed version: [details/wallet-details.md](details/wallet-details.md) (every detailed doc is in [`details/`](details/)).

Based on the latest `develified.apk` from the
[Project Real Resurrection Discord](https://discord.com/invite/project-resurrection-official-server-1482888689854971997)
(Mali GPU variant).

> **Project Real Resurrection.** Part of Project Real Resurrection's work on Real
> Racing 3. Not affiliated with, endorsed or supported by Electronic Arts.

## Steps

1. Copy `files/doc/character.2.dat` off the phone (game closed); keep the
   original. See [save-file.md](save-file.md).
2. Show the balances:
   `python3 tools/rr3_wallet.py show character.2.dat`
3. Write a copy with new balances (any of the three):
   ```sh
   python3 tools/rr3_wallet.py set character.2.dat edited.dat --gold 50000 --rd 10000000 --md 10000000
   ```
4. Rename `edited.dat` to `character.2.dat`, put it back in `files/doc/`,
   start the game.

Ready-made example: `saves/edited/character.2.dat` (Gold 50,000, R$ and M$
10,000,000).

---

Detailed version: [details/wallet-details.md](details/wallet-details.md). Every detailed doc is in
[`details/`](details/).
