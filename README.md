# RR3

Notes and tooling for understanding, and eventually modifying, Real Racing 3 game files.

Part of Project Real Resurrection's work on Real Racing 3. Not affiliated with,
endorsed or supported by Electronic Arts.

## Docs

Step-by-step guides for every modification, one per feature: [docs/README.md](docs/README.md).

What changed in each version of the patched game: [CHANGELOG.md](CHANGELOG.md).
Versions and build numbers: [docs/builds.md](docs/builds.md).

Most common tasks:

| I want to... | Guide |
|---|---|
| Get my save and game files off the phone | [docs/getting-files.md](docs/getting-files.md) |
| Edit my save (`character.2.dat`): how it works, back up, put it back | [docs/save-file.md](docs/save-file.md) |
| Set Gold, R$, M$ | [docs/wallet.md](docs/wallet.md) |
| Own cars, VIP on/off, reset upgrades to stock | [docs/cars-and-vip.md](docs/cars-and-vip.md) |
| Reset event progress | [docs/event-progress.md](docs/event-progress.md) |
| Patch the game library (Time Trial, store) and reinstall | [docs/patched-library.md](docs/patched-library.md), [docs/installing.md](docs/installing.md) |

## Purpose

- Document the formats of RR3 data files (what they contain and how they are structured).
- Keep findings reproducible: each analyzed file gets notes, and any scripts used to parse it.
- Later, build on that understanding to modify files safely.

## Structure

```
docs/       Guides for every modification, one summary + one detailed doc per feature
tools/      Python scripts that do the edits and patches (see tools/README.md)
tables/     Lookup tables built from the game data (events, cars, fuel events)
analysis/   Research notes: how things were found, raw findings (archive/ = older notes)
game/       stock-libRealRacing3.so.gz (as shipped in develified.apk, Mali build); no patched builds
saves/      Save files: reference/ (Tom's save + settings), edited/, community/, outdated/
```

New here? Start with [docs/README.md](docs/README.md). Run every command from
the repo root.

## Notes

- Keep untouched game files in `game/`; write modified copies elsewhere.
- Patched libraries and test saves are in the project files, not in the repo.
- Record the game version and platform a file came from when known.
