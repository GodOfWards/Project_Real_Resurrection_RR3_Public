# Game data files (summary)

The game's databases (events, car list) ship as encrypted `.nct` files. The
tools decrypt them and build the lookup tables in `tables/` that the save tools
use for names. Detailed version: [details/game-data-details.md](details/game-data-details.md) (every detailed doc is in [`details/`](details/)).

Based on the latest `develified.apk` from the
[Project Real Resurrection Discord](https://discord.com/invite/project-resurrection-official-server-1482888689854971997)
(Mali GPU variant; the key is read from its `libRealRacing3.so`).

> **Project Real Resurrection.** Part of Project Real Resurrection's work on Real
> Racing 3. Not affiliated with, endorsed or supported by Electronic Arts.

The tables are already in the repo; you only need this when the game data
changes.

| File in game data | Table in the repo |
|---|---|
| `data/events.dat.nct` | `tables/event-index.csv` (every event), `tables/fuel-events.csv` |
| `vehicles/data/cardesc.list.nct` | `tables/car-index.csv` (every car) |

## Steps

1. Copy the `.nct` files from the game data (`files/.depot` or `files/apk`
   under `Android/data/com.ea.games.r3_row/`, or the `files` zip).
2. Decrypt:
   ```sh
   python3 tools/rr3_nct.py events.dat.nct events.dat --lib stock-libRealRacing3.so
   python3 tools/rr3_nct.py cardesc.list.nct cardesc.list --lib stock-libRealRacing3.so
   ```
   The key is read from the stock game library
   ([getting-files.md](getting-files.md)); without `--lib` the tool uses the
   repo copy `game/stock-libRealRacing3.so.gz`.
3. Build the tables:
   ```sh
   python3 tools/rr3_event_index.py events.dat tables/event-index.csv
   python3 tools/rr3_car_index.py cardesc.list tables/car-index.csv
   python3 tools/rr3_fuel.py events.dat tables/fuel-events.csv
   ```

---

Detailed version: [details/game-data-details.md](details/game-data-details.md). Every detailed doc is in
[`details/`](details/).
