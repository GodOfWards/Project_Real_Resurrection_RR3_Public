# Tools

Python 3 scripts, no extra packages (except `rr3_livery.py`: numpy, Pillow). Run them from the repo root
(`python3 tools/NAME.py ...`); usage is at the top of each script. The
guide for each one is in [`docs/`](../docs/README.md).

## Save file (`character.2.dat`)

| Script | What it does | Guide |
|---|---|---|
| `rr3_dat.py` | Decrypt / re-encrypt saves, compare two saves | [save-file.md](../docs/save-file.md) |
| `rr3_wallet.py` | Read or set Gold, R$, M$ | [wallet.md](../docs/wallet.md) |
| `rr3_events.py` | List or reset event progress | [event-progress.md](../docs/event-progress.md) |
| `rr3_cars.py` | Own cars, VIP on/off, remove upgrades, find car ids | [cars-and-vip.md](../docs/cars-and-vip.md) |

## Lib and APK patches (`libRealRacing3.so` Mali build, `rr3_cleartext.py` the APK)

Each changes the stock lib (as shipped in `develified.apk`); `check LIB`
shows what a lib already has.

| Script | What it does | Guide |
|---|---|---|
| `rr3_tt_laps.py` | Time Trial lap modes | [time-trial-laps.md](../docs/time-trial-laps.md) |
| `rr3_drive_cost.py` | Time Trial without drive point cost | [time-trial-drive-points.md](../docs/time-trial-drive-points.md) |
| `rr3_mtx.py` | Store purchases without Google Play | [store-purchases.md](../docs/store-purchases.md) |
| `rr3_cc_local.py` | Send Cloudcell sync requests to our own server (test) | [cloudcell-test-server.md](../docs/cloudcell-test-server.md) |
| `rr3_cleartext.py` | Make the APK allow plain http (network security config) | [cloudcell-test-server.md](../docs/cloudcell-test-server.md) |
| `rr3_omp.py` | Online Multiplayer patches (issue #86): part `nosocial`, Race Now without a social network log-in; part `host` (`--mp-host`), the master server address | [multiplayer.md](../docs/multiplayer.md) |
| `rr3_login_popup.py` | Remove the "PLEASE LOG IN" pop-up on Time Trial leaderboards (b21) | [cloudcell-test-server.md](../docs/cloudcell-test-server.md) |
| `rr3_debug_menu.py` | Open EA's debug menu with a triple-tap in the bottom-right corner; keeps AI Skill and Debug Race Selector ON/OFF in `files/doc/debug_menu_settings.dat` (`settings@v2`; emulator check: `tests/rr3_debug_menu_settings_test.py`, needs unicorn). `--limited` (debug menu limited): only AI, Debug Race Selector and Character, for public builds (code: `asm/rr3_debug_menu_settings.s`, `asm/rr3_debug_menu_filter.s`) | [debug-menu.md](../docs/debug-menu.md), [ai-difficulty.md](../docs/ai-difficulty.md) |
| `rr3_username.py` | ENTER RACING CODE button sets a leaderboard username, kept in `files/doc/leaderboard_username.dat` and sent to `rr3_cc_server.py`; needs `rr3_debug_menu.py` part `nosales` (code: `asm/rr3_username.s`; emulator check: `tests/rr3_username_test.py`, needs unicorn); `show`/`write` read or make the file | [leaderboard-username.md](../docs/leaderboard-username.md) |
| `rr3_selector_times.py` | Race Selector: Time Trial best and ghost per track and car, kept in `files/doc/race_selector_times.dat` (code: `asm/rr3_selector_times.s`; emulator check: `tests/rr3_selector_times_test.py`, needs unicorn); `list` shows the file | [race-selector-times.md](../docs/race-selector-times.md) |
| `rr3_friends_mail.py` | Keep "someone beat your time" mail (10459) for every event, not only events with friends' results (check: `tests/rr3_friends_mail_test.py`) | [friends-mail.md](../docs/friends-mail.md) |

## Builds

| Script | What it does | Guide |
|---|---|---|
| `rr3_build.py` | Which Project Real Resurrection version and build (`b00`, `b01`, ...) a library or APK is, incl. the installed one; `patches` reads what a library contains from its bytes; add new builds to `tables/builds.csv` | [builds.md](../docs/builds.md) |
| `rr3_patch_sites.py` | Every lib address range each patch tool writes, in `tables/lib-patch-sites.csv` (`update` makes it from the tools, `check` finds overlaps between tools, an out-of-date table, or a patch tool missing from its list (the list `rr3_build.py patches` uses), `find` tells whether planned addresses are free). Run `check` after changing a patch tool | this script's `-h` |

## Leaderboard server (runs on a phone or PC, not in the game)

| Script | What it does | Guide |
|---|---|---|
| `rr3_cc_server.py` | Cloudcell server (Termux or PC): records requests, answers leaderboards with real Time Trial times and stores and serves ghosts; players keyed by an HMAC made with `server.key`; shows in-game usernames (`rr3_username.py`, check: `tests/rr3_cc_username_test.py`); a member id per player in `--members` (check: `tests/rr3_cc_members_test.py`); `--omp FILE` answers the online multiplayer schedule (example: `rr3-omp-schedule.example.json`, check: `tests/rr3_cc_omp_test.py`); v5.1 limits bodies, wrapper layers and unpacked size and refuses impossible results (check: `tests/rr3_cc_limits_test.py`); saves requests only with `--save`; v5.5 drops Race Selector results and ghosts (event 18130, check: `tests/rr3_cc_selector_test.py`); v5.6 answers Ghost Challenge rows (10516) and sends "someone beat your time" mail (10459, `--mail`; check: `tests/rr3_cc_mail_test.py`); v5.7 answers friends' results (10419, no rows yet; check: `tests/rr3_cc_friends_test.py`) | [cloudcell-test-server.md](../docs/cloudcell-test-server.md) |
| `rr3_mp_server.py` | Online Multiplayer master server on UDP 60000; v0.3 logs the game's datagrams by fmRUDP packet type, answers the transport (connect, data acks, pings) and the master server hello with a game server list (UDP 60001, a second listener); v0.4 runs rooms (roster, race start); v0.5 checks car ids and names from phones, survives a bad datagram and saves only with `--save`; v0.7-v0.10 relay, start time, grid; v0.11 relays only known race messages (rate limited), checks connection ids, forgets silent phones (confirmed in game); v0.12 also relays penalties (57) (check: `tests/rr3_mp_server_test.py`) | [multiplayer.md](../docs/multiplayer.md) |
| `rr3_cc_blob.py` | Decode recorded Cloudcell requests (wrapper, subsyncs, race history) and build the server's replies | [cloudcell-sync-format.md](../docs/details/cloudcell-sync-format.md) |

## Game data (`.nct` files) and tables

| Script | What it does | Guide |
|---|---|---|
| `rr3_nct.py` | Decrypt `.nct` files (key read from the library) | [game-data.md](../docs/game-data.md) |
| `rr3_event_index.py` | Build `tables/event-index.csv` | [game-data.md](../docs/game-data.md) |
| `rr3_car_index.py` | Build `tables/car-index.csv` | [car-index.md](../docs/car-index.md) |
| `rr3_fuel.py` | Build `tables/fuel-events.csv` | [fuel-consumption.md](../docs/fuel-consumption.md) |
| `rr3_livery.py` | Livery texture to PNG and back (needs numpy, Pillow) | [liveries.md](../docs/liveries.md) |

`rr3_cars.py` and `rr3_events.py` read names from `../tables/`, and
`rr3_nct.py` defaults to `../game/stock-libRealRacing3.so.gz`, so keep the
`tools/`, `tables/` and `game/` folders side by side.

## Tests (`tests/`)

Checks that run a tool without the game: the server tests send it made-up
requests, the patch tests run its new ARM code in an emulator (needs
unicorn). Run one with `python3 tools/tests/NAME_test.py`.

- A test is not thrown away after it passes: it stays in `tests/` and is
  run again whenever its tool changes.
- When a tool gets a new version, its test is updated in place to check
  that version. There is no folder of old tests; git history keeps them.
- An older version the tool can still write (an option like
  `--best-version`) keeps its case in the same test.
- Run the tool's test before a PR that changes the tool.
