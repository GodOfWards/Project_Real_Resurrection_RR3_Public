# Time Trial laps (summary)

In the stock game a Time Trial ends after one timed lap. This library patch
lets you keep lapping. Applies to every Time Trial event; other race types
are unaffected. Detailed version (every byte, how it was found):
[details/time-trial-laps-details.md](details/time-trial-laps-details.md) (every detailed doc is in [`details/`](details/)).

> **Mali GPU variant only.** Made on the `libRealRacing3.so` of the latest
> `develified.apk` in the
> [Project Real Resurrection Discord](https://discord.com/invite/project-resurrection-official-server-1482888689854971997)
> (as of 2026-10-07). The tool refuses any other library. Other GPU variants
> may well share it, but that is unconfirmed (`analysis/gpu-variants.md`).

> **Project Real Resurrection.** Part of Project Real Resurrection's work on Real
> Racing 3. Not affiliated with, endorsed or supported by Electronic Arts.

## Variants

| `--laps` | What happens | Time saved? | Tested |
|---|---|---|---|
| `best` (recommended) | Timer restarts every lap; a valid lap that beats your best finishes the session with the normal results screen | Yes, the new best | v2 and v4 yes |
| `reset` | Timer restarts every lap, never finishes; leave from the pause menu | No | Yes |
| `2`, `3`, `5`, `9`, `17` | Finishes after that many laps, timer runs from lap 1 | Unclear | `9` only |
| `unlimited` | Never finishes | No | No |

With `best` and no stored best yet, the first lap finishes, as in the stock
game (confirmed 2026-10-12, issue #7). Leaving from the pause menu never saves
a time.

Up to v3, an off-track lap invalidated the whole session, not just that lap:
if a later lap beat the best, the event completed but Results showed "Time
not recorded" (confirmed 2026-10-12, issue #6). v4 fixes this: an off-track
(or too-much-damage) lap restarts like a slower lap and the next lap is valid
again, so only that lap is lost. With no stored best yet, the session now
finishes on the first valid lap instead of the first lap. Long sessions are fine: about 25 laps at
Brands Hatch ran with no performance problems (2026-10-12, issue #9).

## Steps

1. Easiest: use the ready-made combined build (laps `best` + store + no drive
   cost), see [patched-library.md](patched-library.md).
2. Or build just this patch from the stock library
   ([getting-files.md](getting-files.md)):
   ```sh
   python3 tools/rr3_tt_laps.py patch stock-libRealRacing3.so libRealRacing3.so --laps best
   python3 tools/rr3_tt_laps.py check libRealRacing3.so
   ```
3. Put it in the APK and install: [installing.md](installing.md).
4. If it crashes: [crash-logs.md](crash-logs.md).

Status: `best` CONFIRMED in game 2026-10-07 (a slower lap kept going, the
next lap was a new best, the session finished and the time was saved).

`best` v4 (2026-10-13, current tool) CONFIRMED in game 2026-10-20 (b30,
Race Selector, Ford Focus at Brands Hatch): with no stored best the first
lap finished; off-track laps (slower or faster) restarted; the next valid
faster lap finished and the new best was saved and submitted. It includes
two fixes:

- v3: v2 saved a new best set after restarted laps with the first lap's
  per-point times, so the live delta compared against a slower lap
  ([time-trial-delta.md](time-trial-delta.md)).
- v4: an invalid (off-track or damage) lap no longer voids the session
  (issue #6).

`--laps best` writes v4. To test one fix at a time, add `--best-version 2`
or `--best-version 3`; `check` names the version a library has.

---

Detailed version: [details/time-trial-laps-details.md](details/time-trial-laps-details.md). Every detailed doc is in
[`details/`](details/).
