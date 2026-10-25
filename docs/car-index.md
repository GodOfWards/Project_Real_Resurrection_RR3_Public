# Car index (summary)

`tables/car-index.csv` lists all 540 cars with the id the game and the save use.
Use that id with `tools/rr3_cars.py` ([cars-and-vip.md](cars-and-vip.md)).
Detailed version: [details/car-index-details.md](details/car-index-details.md) (every detailed doc is in [`details/`](details/)).

Based on the latest `develified.apk` from the
[Project Real Resurrection Discord](https://discord.com/invite/project-resurrection-official-server-1482888689854971997)
(Mali GPU variant).

> **Project Real Resurrection.** Part of Project Real Resurrection's work on Real
> Racing 3. Not affiliated with, endorsed or supported by Electronic Arts.

## Look up a car

    python3 tools/rr3_cars.py find skyline
    python3 tools/rr3_cars.py find 2019 red bull
    python3 tools/rr3_cars.py find 114

Every word must match (name or id, any case). Or open the CSV in a
spreadsheet: columns `car_id, name, year, make, model, team, file`.

Names are cleaned up from the game's file names, so spelling can differ a
little from what the game shows. Road/Motorsport is not in the list.

---

Detailed version: [details/car-index-details.md](details/car-index-details.md). Every detailed doc is in
[`details/`](details/).
