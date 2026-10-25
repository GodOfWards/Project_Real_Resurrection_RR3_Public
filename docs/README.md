# Docs: every modification, by feature

Step-by-step guides for each change made to Real Racing 3 (v14.0.1, Android
arm64, `com.ea.games.r3_row`) in this repo. Every feature has two docs:

- **Summary**: what it does, its status, and the shortest way to use it.
- **Details**: the exact fields, bytes and addresses, every step of the
  procedure, how it was found, and what was tried and failed.

All work is based on the latest `develified.apk` from the
[Project Real Resurrection Discord](https://discord.com/invite/project-resurrection-official-server-1482888689854971997),
**Mali GPU variant**. Every `libRealRacing3.so` address in these docs is for
that build only (stock md5 `0e8cc145c5a8b5d9e8ee9a4cb9483793`); the patch
tools refuse any other library. Other GPU variants are untested, see
[`analysis/gpu-variants.md`](../analysis/gpu-variants.md).

> **Project Real Resurrection.** Part of Project Real Resurrection's work on Real
> Racing 3. Not affiliated with, endorsed or supported by Electronic Arts.

## Save edits (`character.2.dat`, no APK change)

| Feature | Summary | Details | Tool | Status |
|---|---|---|---|---|
| Save format, encryption, checksum | [save-file.md](save-file.md) | [details/save-file-details.md](details/save-file-details.md) | `rr3_dat.py` | Done |
| Currency balances (Gold, R$, M$) | [wallet.md](wallet.md) | [details/wallet-details.md](details/wallet-details.md) | `rr3_wallet.py` | Confirmed in game |
| Reset event progress | [event-progress.md](event-progress.md) | [details/event-progress-details.md](details/event-progress-details.md) | `rr3_events.py` | Confirmed in game |
| Own cars, VIP, remove upgrades | [cars-and-vip.md](cars-and-vip.md) | [details/cars-and-vip-details.md](details/cars-and-vip-details.md) | `rr3_cars.py` | Confirmed in game |
| Car ids and names | [car-index.md](car-index.md) | [details/car-index-details.md](details/car-index-details.md) | `rr3_car_index.py`, `rr3_cars.py find` | Done |

## Game library patches (`libRealRacing3.so`, needs a re-signed APK)

| Feature | Summary | Details | Tool | Status |
|---|---|---|---|---|
| Time Trial: more laps / finish on a new best | [time-trial-laps.md](time-trial-laps.md) | [details/time-trial-laps-details.md](details/time-trial-laps-details.md) | `rr3_tt_laps.py` | Confirmed in game (`best` v2 and v4, `reset`, `9`) |
| Time Trial: no drive point ("energy") cost | [time-trial-drive-points.md](time-trial-drive-points.md) | [details/time-trial-drive-points-details.md](details/time-trial-drive-points-details.md) | `rr3_drive_cost.py` | Confirmed in game |
| Store purchases without Google Play | [store-purchases.md](store-purchases.md) | [details/store-purchases-details.md](details/store-purchases-details.md) | `rr3_mtx.py` | Confirmed in game |
| EA debug menu (triple-tap bottom-right corner) | [debug-menu.md](debug-menu.md) | [details/debug-menu-details.md](details/debug-menu-details.md) | `rr3_debug_menu.py` (full menu, AI Skill and Race Selector kept) | Confirmed in game (menu opens) |
| AI difficulty for players: debug menu limited (only AI, Character and Race Selector) | [ai-difficulty.md](ai-difficulty.md) | [details/ai-difficulty-details.md](details/ai-difficulty-details.md) | `rr3_debug_menu.py --limited` | Confirmed working (b18, 2026-10-13) |
| Race Selector: Time Trial best per track and car (own file `race_selector_times.dat`) | [race-selector-times.md](race-selector-times.md) | [details/race-selector-times-details.md](details/race-selector-times-details.md) | `rr3_selector_times.py` | v2 written (real car id, issue #106), emulator check only; v1 in b25/b26/b30 shared one best per track |
| Leaderboard username from the ENTER RACING CODE button (own file `leaderboard_username.dat`, shown by `rr3_cc_server.py`) | [leaderboard-username.md](leaderboard-username.md) | [details/leaderboard-username-details.md](details/leaderboard-username-details.md) | `rr3_username.py` | Confirmed in game (v1 and v2, 2026-10-19) |
| "Someone beat your time" mail kept for every event (no friends' results needed) | [friends-mail.md](friends-mail.md) | [details/friends-mail-details.md](details/friends-mail-details.md) | `rr3_friends_mail.py` | Written 2026-10-24 (issue #163), not tested in game |
| Versions and build numbers: which patched library is which | [builds.md](builds.md) | [details/builds-details.md](details/builds-details.md) | `rr3_build.py` | Done |
| Local leaderboard: game's Cloudcell syncs to a server in Termux; your real Time Trial times in the leaderboards, no log-in pop-up (b21) | [cloudcell-test-server.md](cloudcell-test-server.md) | [details/cloudcell-test-server-details.md](details/cloudcell-test-server-details.md), [details/cloudcell-sync-format.md](details/cloudcell-sync-format.md) | `rr3_cc_local.py`, `rr3_cleartext.py`, `rr3_login_popup.py`, `rr3_cc_server.py`, `rr3_cc_blob.py` | Working (own times only) |
| Community leaderboard server: what a shared internet server needs and how to point the game at it | [community-leaderboard-server.md](community-leaderboard-server.md) | [details/cloudcell-sync-format.md](details/cloudcell-sync-format.md) | `rr3_cc_local.py`, `rr3_cc_server.py`, `rr3_cc_blob.py` | Plan, not tested |
| Combined library (all three) | [patched-library.md](patched-library.md) | [details/patched-library-details.md](details/patched-library-details.md) | all three | Confirmed in game |

## Game data and research

| Topic | Summary | Details | Tool |
|---|---|---|---|
| Decrypting `.nct` game data, event index | [game-data.md](game-data.md) | [details/game-data-details.md](details/game-data-details.md) | `rr3_nct.py`, `rr3_event_index.py` |
| Custom liveries (PNG to car texture) | [liveries.md](liveries.md) | [details/liveries-details.md](details/liveries-details.md) | `rr3_livery.py` |
| Time Trial live delta (research only, no patch) | [time-trial-delta.md](time-trial-delta.md) | [details/time-trial-delta-details.md](details/time-trial-delta-details.md) | - |
| Game text files (`gametext.txt`, `text_<lang>.txt`): RC4 format, key/value layout (research only, issue #92) | research note: [analysis/gametext.md](../analysis/gametext.md) | same | - |
| GUI layout files (`.depot/gui/processed/*.gui`): RC4 + XML format (same key as `.nct`), per-mode override folders, device-profile fallback (research only, paused, issue #113) | research note: [analysis/gui-format.md](../analysis/gui-format.md) | same | - |
| Leaderboard ghosts: online upload/download, Ghost Challenge, member ids (research only, issues #94, #95) | research note: [analysis/leaderboard-ghosts.md](../analysis/leaderboard-ghosts.md) | same | - |
| Friends without Facebook: how the phone gets its friends' results (subsync 10419), what mail needs (research only, issue #163) | research note: [analysis/friends.md](../analysis/friends.md) | same | - |
| Community screen: our links through server variables (subsync 10712), Instagram button to Party Play (plan and research only, issue #145) | [community-screen.md](community-screen.md) | [details/community-screen-details.md](details/community-screen-details.md), research note [analysis/community-screen.md](../analysis/community-screen.md) | - |
| Race camera tweaks: per-view FOV/zoom and per-car position/rotation, `camTweaks.dat` (research only) | research note: [analysis/camera.md](../analysis/camera.md) | same | - |
| Server safety before a public build: `rr3_cc_server.py`, `rr3_mp_server.py` (review only, issue #143) | research note: [analysis/server-safety.md](../analysis/server-safety.md) | same | - |
| Party Play (local split-screen): controller gate, forced player count, debug menu entries (research only, issue #126) | [party-play.md](party-play.md) | [details/party-play-details.md](details/party-play-details.md) | - |
| Fuel consumption (research only, no patch) | [fuel-consumption.md](fuel-consumption.md) | [details/fuel-consumption-details.md](details/fuel-consumption-details.md) | `rr3_fuel.py` |
| Multiplayer and leaderboards: servers and protocols; OMP schedule from our server, Race Now without a social log-in, master server address, own master server (game connects; lobby not yet; issue #86) | [multiplayer.md](multiplayer.md) | [details/multiplayer-details.md](details/multiplayer-details.md) | `rr3_cc_server.py --omp`, `rr3_omp.py`, `rr3_mp_server.py` |
| Track time of day (fixed per variant) and the 20-lap limit (research only, no patch) | [time-of-day-and-lap-limit.md](time-of-day-and-lap-limit.md) | [details/time-of-day-and-lap-limit-details.md](details/time-of-day-and-lap-limit-details.md) | - |
| Music: FMOD MP3s in `audio/music/`, screen songs in the lib, 3 shuffled songs per track file (research only, untested, issue #37) | [music.md](music.md) | [details/music-details.md](details/music-details.md), list [analysis/track-music.csv](../analysis/track-music.csv) | - |

## Device side

| Topic | Summary | Details |
|---|---|---|
| Getting the library, game data and save (Termux + Shizuku or root) | [getting-files.md](getting-files.md) | [details/getting-files-details.md](details/getting-files-details.md) |
| Player guide: set up Termux + rish, fix 0-byte save copies after a reinstall, save a crash log | [rish-guide.md](rish-guide.md) | [details/rish-guide-details.md](details/rish-guide-details.md) |
| Re-signing, first install, updates | [installing.md](installing.md) | [details/installing-details.md](details/installing-details.md) |
| Crash logs | [crash-logs.md](crash-logs.md) | [details/crash-logs-details.md](details/crash-logs-details.md) |
| Command templates: build, install, save backup/swap, installed build, crash log | [commands.md](commands.md) | [details/commands-details.md](details/commands-details.md) |

## Where to start

1. Get the files from your phone: [getting-files.md](getting-files.md).
2. Library mods: [patched-library.md](patched-library.md), then
   [installing.md](installing.md).
3. Save edits: [save-file.md](save-file.md), then the feature you need. Always keep a copy of the original save.

Research notes (how things were found, raw findings) are in
[`analysis/`](../analysis/). The tools need only Python 3 (`rr3_livery.py` also needs numpy and Pillow). Commands assume
you run them from the repo root; [`tools/README.md`](../tools/README.md) lists them.
