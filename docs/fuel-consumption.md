# Fuel consumption (summary)

Research only: **nothing is patched yet.** Some special events give you a
fuel tank that drains while you drive; when it is empty the race ends.
Detailed version: [details/fuel-consumption-details.md](details/fuel-consumption-details.md) (every detailed doc is in [`details/`](details/)).

Based on the latest `develified.apk` from the
[Project Real Resurrection Discord](https://discord.com/invite/project-resurrection-official-server-1482888689854971997)
(Mali GPU variant).

> **Project Real Resurrection.** Part of Project Real Resurrection's work on Real
> Racing 3. Not affiliated with, endorsed or supported by Electronic Arts.

## Findings

- 265 events use fuel (205 Cup, 37 Fuel, 18 NASCAR, 3 Endurance, 2
  Elimination), including Rd Le Mans 2020 (event 41947). Full list:
  `tables/fuel-events.csv`.
- Tank size and burn rate are set per event in the game data, not in the
  game code.
- Fuel burns only on the throttle, slower in a slipstream.
- There are no pit stops or refuelling.

## Look up an event

```sh
grep 41947 tables/fuel-events.csv
```

The `throttle_seconds` column is how long you can stay on the throttle
before the tank is empty.

## Possible next steps

Make the tank bigger or the burn rate 0 in the event data, or patch the game
code so fuel never drops. Not started.

---

Detailed version: [details/fuel-consumption-details.md](details/fuel-consumption-details.md). Every detailed doc is in
[`details/`](details/).
