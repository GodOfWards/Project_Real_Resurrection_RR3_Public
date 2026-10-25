# Time Trial: how the live delta works (summary)

The live delta is the `+0.123` / `-0.456` shown while you drive a Time Trial:
how far ahead (green, negative) or behind (red, positive) you are compared with
your best lap at the same point of the track. This page explains where that
reference comes from, and a bug in our `best` lap patch that left it on an
older lap (fixed in `best` v3). Detailed version:
[details/time-trial-delta-details.md](details/time-trial-delta-details.md) (every detailed doc is in [`details/`](details/)).

> **Mali GPU variant only.** Addresses are in the `libRealRacing3.so` of the
> latest `develified.apk` in the
> [Project Real Resurrection Discord](https://discord.com/invite/project-resurrection-official-server-1482888689854971997).

> **Project Real Resurrection.** Part of Project Real Resurrection's work on Real
> Racing 3. Not affiliated with, endorsed or supported by Electronic Arts.

## In short

- **The delta follows the ghost, not the save.** Every frame the game takes
  your time on the current lap and subtracts the time the ghost lap had at the
  same point of the track. The ghost lap is a recording (time per track point),
  not just a lap time.
- **The ghost recording is loaded when the session starts** (and on Restart).
  It is not reloaded during the session.
- **A new best replaces the ghost at the end of the race.** If your lap beats
  the current ghost, the game turns your lap into the new ghost. The delta uses
  it from the next session (or Restart) on.
- **`character.2.dat` only keeps the best time per event**
  (`m_mEventProgress` → `m_bestRaceTime`, in ms). That is what the results
  screen compares against, and what the `best` lap patch checks. It does not
  hold the per-point times the live delta needs.
- **The per-track records in the save are unused.** `m_trackStats.m_tracks`
  has `bestTimeTrialLap` and three `bestTimeTrialLapCheckpointTimes` per
  track, but nothing in this library reads or writes them, and they are empty
  in every save we have.

## If the delta compares against an older lap

**Cause: our `best` lap patch (v2), not the game.** The ghost recording keeps
one time per track point. The game fills each point only once per session (it
only writes points that are still empty) and never empties them between laps,
because in the stock game a session has one timed lap. The `best` patch
restarts the lap until you beat your best, so from the second lap on the
recorder kept the first lap's times. A new best set after restarted laps was
saved with the car positions of the best lap (so the ghost car looked right)
but the times of the session's first, slower lap. The delta then compared
against that slower lap.

A best set on the first lap of a session was saved correctly, which is why it
seemed to fix itself on 2026-10-12. It came back on 2026-10-13.

**Fix: `best` v3** (`tools/rr3_tt_laps.py --laps best`; builds
`b11`/`b12`, [game/README.md](../game/README.md)). Before restarting a lap
it empties the recording's per-point times, so each lap records its own.

An already saved bad ghost stays until you set a new best with v3. Editing
`character.2.dat` does not change the delta.

---

Detailed version: [details/time-trial-delta-details.md](details/time-trial-delta-details.md). Every detailed doc is in
[`details/`](details/).
