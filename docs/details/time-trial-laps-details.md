# Time Trial laps (detailed)

Every instruction the lap patch changes, every game function and field it
relies on, how it was found, and the attempts that did not work. Summary:
[time-trial-laps.md](../time-trial-laps.md). Research notes:
[`analysis/libRealRacing3.so.md`](../../analysis/libRealRacing3.so.md).

- Target: `lib/arm64-v8a/libRealRacing3.so` from RR3 v14.0.1, Project Real
  Resurrection, one APK for every GPU (the latest `develified.apk` in the Project Real
  Resurrection [Discord](https://discord.com/invite/project-resurrection-official-server-1482888689854971997) as of 2026-10-07). BuildID
  `2de55b89018a3c996c8ef863db591296`, develified md5
  `0e8cc145c5a8b5d9e8ee9a4cb9483793`, 33110472 bytes.
- In this library, executable code has address == file offset, so every
  address below is also the byte position in the file.
- Instruction bytes are shown as stored in the file (little-endian).
- Nothing else in the APK changes except its signature (the APK is re-signed).

> **Project Real Resurrection.** Part of Project Real Resurrection's work on Real
> Racing 3. Not affiliated with, endorsed or supported by Electronic Arts.

## 0. What ends a Time Trial, and how it was found

There are two lap counts in the game, and neither controls Time Trial:

1. **Game mode lap count.** `GameMode` vtable slot 2, `0xf1ae8c`, returns
   `max(1, this+0x24)`. The `GameMode` constructor (`0xf168e8`) sets `+0x24`
   to 1; `TimeTrialMode` (constructor `0x1040d9c`, via `SoloMode`
   `0xfeae18`) never changes it. Patched to return 10 (PR #3): **no effect**
   in game.
2. **Race lap count.** `SetRaceLapCount` (`0x10b2d18`) clamps to 1..20 and
   stores `game+0x10c80` (this is the 20-lap limit of normal races; event
   data above 20 is only warned about by the loader at `0xc67a2c`, see
   [time-of-day-and-lap-limit-details.md](time-of-day-and-lap-limit-details.md)). It is fed by
   `GetModeLapCount` (`0xb05704`), a switch on the mode type with a byte jump
   table at `0x4b7e24`; Time Trial is mode type 18 (factory `0xb08994`) and
   gets a hard-coded 1. Patched the jump-table entry to a stub returning 10
   (PR #4, first version): **no effect** in game.

What actually ends it: `TimeTrialMode` runs a state machine at `+0x180`
(tick `0x10432bc`: 0 = waiting for the rolling start, 1 = timed lap,
3 = finished). In state 1 it ticks a lap-timing object at `+0x1b0` (ctor
`0x102ebd0`, tick `0x102ea04`, whose only caller is `0x1043444`, so this code
is Time Trial only) and moves to state 3 when that object's state `[+0]`
becomes 2 (checked at `0x102e5d4`). The tick counts finish-line crossings and
sets state 2 on the first crossing after the timed lap starts. That single
decision is what every variant changes.

Neither failed attempt is applied by the current tool.

## 1. Changed instructions, per variant

Each variant is applied to the develified library on its own. Variants never stack.

### `--laps 2 / 3 / 5 / 9 / 17 / unlimited` (one instruction)

| Address | Develified | Patched |
|---|---|---|
| `0x102ea8c` | `28 06 f8 37`  `tbnz w8, #31, 0x102eb50` | see below |

| Option | Laps | Bytes | Instruction |
|---|---|---|---|
| `2` | 2 | `28 06 00 36` | `tbz w8, #0, 0x102eb50` |
| `3` | 3 | `28 06 08 36` | `tbz w8, #1, 0x102eb50` |
| `5` | 5 | `28 06 10 36` | `tbz w8, #2, 0x102eb50` |
| `9` | 9 | `28 06 18 36` | `tbz w8, #3, 0x102eb50` |
| `17` | 17 | `28 06 20 36` | `tbz w8, #4, 0x102eb50` |
| `unlimited` | never ends (2^30+1) | `28 06 f0 36` | `tbz w8, #30, 0x102eb50` |

`w8` is the number of line crossings before this one. Develified skips the finish
only when `w8` is negative, which never happens on a normal lap, so the first
lap always finishes. With `tbz w8, #k` the finish is skipped until bit k of
`w8` is set, which first happens on crossing 2^k, i.e. after 2^k + 1 laps.

### `--laps reset` (one instruction)

| Address | Develified | Patched |
|---|---|---|
| `0x102ea8c` | `28 06 f8 37`  `tbnz w8, #31, 0x102eb50` | `1f 00 00 14`  `b 0x102eb08` |

Every crossing jumps to the game's own "start the timed lap" code at
`0x102eb08`, which is the same code the very first crossing runs.

### `--laps best` (one instruction + 164 bytes of new code, v5)

| Address | Develified | Patched |
|---|---|---|
| `0x102eab4` | `60 32 40 f9`  `ldr x0, [x19, #0x60]` | `23 48 2a 14`  `b 0x1ac0b40` |
| `0x1ac0b40`–`0x1ac0be3` | all `00` (padding) | the v5 routine below |

v5 (2026-11-05, issue #5) is v4 with one check in front: in **Watch
Replay** (a leaderboard ghost replayed from the Time Trial screen) the
timing object's flag `+0x15c` is set (the timing constructor `0x102ebd0`
stores its argument there at `0x102ec58`; `TimeTrialMode+0x5f4 == 1`;
that only Watch Replay sets it is inferred, not traced per menu entry:
`analysis/tt-best-ghost.md` section 5), and
the routine then takes the develified finish at once. Up to v4, a replayed
ghost lap went through the best check like a driven lap: when the viewer's
own best was faster, the replay "was not a best", the timer restarted and
the replay looped (analysis: `analysis/tt-best-ghost.md`). The develified
restart path also reads `+0x15c` (`0x102eb08`).

To stay inside v4's bytes, v5 no longer saves and restores `x21`. On entry
`x21` = timing+0x70 (`0x102ea50 add x21, x19, #0x70`). The finish path
(`0x102eab8`–`0x102ead0`, then `0x102eb50`) does not read `x21` before the
tick's epilogue restores it (`0x102eb5c ldr x21, [sp, #24]`), so on the
finish it may hold the lap time. The restart path reads it
(`0x102eb30 mov x0, x21`), so `restart` sets it again. `b.lt finish` +
`b clear` became `b.ge clear`.

```
addr      bytes         instruction                    purpose
1ac0b40   69 72 45 39   ldrb w9, [x19, #0x15c]         Watch Replay flag (new in v5)
1ac0b44   09 03 00 35   cbnz w9, finish                replay: finish as develified
1ac0b48   69 4e 44 b9   ldr  w9, [x19, #0x44c]         w9 = session validity = [TimeTrialMode+0x5fc]
1ac0b4c   3f 05 00 31   cmn  w9, #0x1
1ac0b50   80 00 00 54   b.eq valid                     -1 = valid, go on
1ac0b54   09 00 80 12   mov  w9, #-1
1ac0b58   69 4e 04 b9   str  w9, [x19, #0x44c]         invalid lap: make the session valid again
1ac0b5c   14 00 00 14   b    clear                     and discard this lap (clear, restart)
valid:
1ac0b60   e0 03 13 aa   mov  x0, x19                   x0 = lap-timing object
1ac0b64   96 b6 d5 97   bl   0x102e5bc                 w0 = lap time just recorded (ms)
1ac0b68   f5 03 00 2a   mov  w21, w0                   keep it (x21 is callee-saved)
1ac0b6c   68 82 5d f8   ldur x8, [x19, #-0x28]         x8 = game = [TimeTrialMode+0x188]
1ac0b70   09 74 82 52   mov  w9, #0x13a0
1ac0b74   29 00 a0 72   movk w9, #0x1, lsl #16         w9 = 0x113a0
1ac0b78   01 69 69 f8   ldr  x1, [x8, x9]              x1 = current event = [game+0x113a0]
1ac0b7c   41 01 00 b4   cbz  x1, finish                no event -> finish normally
1ac0b80   00 e1 11 91   add  x0, x8, #0x478
1ac0b84   37 b4 e9 97   bl   0x152dc60                 x0 = records table (leaf, x1 kept)
1ac0b88   f6 ea bb 97   bl   0x9bb760                  x0 = this event's record, or 0
1ac0b8c   c0 00 00 b4   cbz  x0, finish                no record -> finish normally
1ac0b90   09 08 40 b9   ldr  w9, [x0, #0x8]            w9 = stored best (ms)
1ac0b94   3f 01 00 71   cmp  w9, #0x0
1ac0b98   6d 00 00 54   b.le finish                    no best yet -> finish normally
1ac0b9c   bf 02 09 6b   cmp  w21, w9
1ac0ba0   6a 00 00 54   b.ge clear                     not faster than the best: clear, restart
finish:
1ac0ba4   60 32 40 f9   ldr  x0, [x19, #0x60]          the instruction the hook replaced
1ac0ba8   c4 b7 d5 17   b    0x102eab8                 back into the develified finish
clear:
1ac0bac   68 ee 40 f9   ldr  x8, [x19, #0x1d8]         x8 = player recorder
1ac0bb0   68 01 00 b4   cbz  x8, restart
1ac0bb4   08 09 40 f9   ldr  x8, [x8, #0x10]           x8 = its recording
1ac0bb8   28 01 00 b4   cbz  x8, restart
1ac0bbc   08 5d 40 91   add  x8, x8, #0x17, lsl #12
1ac0bc0   08 21 1c 91   add  x8, x8, #0x708            x8 = &node-time vector (recording+0x17708)
1ac0bc4   09 29 40 a9   ldp  x9, x10, [x8]             begin, end
1ac0bc8   0b 00 80 12   mov  w11, #-1
loop:
1ac0bcc   3f 01 0a eb   cmp  x9, x10
1ac0bd0   62 00 00 54   b.hs restart
1ac0bd4   2b 45 00 b8   str  w11, [x9], #4             times[node] = -1 (empty)
1ac0bd8   fd ff ff 17   b    loop
restart:
1ac0bdc   75 c2 01 91   add  x21, x19, #0x70           x21 as the develified tick expects it
1ac0be0   ca b7 d5 17   b    0x102eb08                 start a new timed lap
```

Hex of the whole routine (`CAVE_CODE` in the tool):

```
6972453909030035694e44b93f0500318000005409008012694e04b914000014
e00313aa96b6d597f503002a68825df8097482522900a072016969f8410100b4
00e1119137b4e997f6eabb97c00000b4090840b93f0100716d000054bf02096b
6a000054603240f9c4b7d51768ee40f9680100b4080940f9280100b4085d4091
08211c91092940a90b0080123f010aeb620000542b4500b8fdffff1775c20191
cab7d517
```

A library patched with v4 and then rebuilt as v5 differs only in
`0x1ac0b40`–`0x1ac0be7` (v4's last four bytes, `0x1ac0be4`–`0x1ac0be7`,
are `00` in v5). Patch sites: `rr3_tt_laps.py` only (best v2–v5);
`username@v5` starts at `0x1ac0be8`, `selector-times@v2` at `0x1ac0c40`.

Emulator check: `tools/tests/rr3_tt_laps_test.py` (needs unicorn) runs the
routine from the hook: with the flag set v5 finishes without a call or a
write, where v4 restarts; with the flag clear v5 ends where v4 ends in every
case (new best, slower, equal, no best, no record, no event, off track,
damage), with the same validity field and node times.

### `--laps best` v4 (one instruction + 168 bytes of new code, older)

`--best-version 4` writes it. Same hook as v5.

| Address | Develified | Patched |
|---|---|---|
| `0x102eab4` | `60 32 40 f9`  `ldr x0, [x19, #0x60]` | `23 48 2a 14`  `b 0x1ac0b40` |
| `0x1ac0b40`–`0x1ac0be7` | all `00` (padding) | the routine below |

`0x102ea8c` is left develified in this variant.

The routine lives in unused zero padding (`0x1ac0b3c`–`0x1ac0fff`, 0x4c4
bytes, all zero in the develified file) inside the executable segment. Nothing
jumps there in the unpatched game.

```
addr      bytes         instruction                    purpose
1ac0b40   69 4e 44 b9   ldr  w9, [x19, #0x44c]         w9 = session validity = [TimeTrialMode+0x5fc]
1ac0b44   3f 05 00 31   cmn  w9, #0x1
1ac0b48   80 00 00 54   b.eq valid                     -1 = valid, go on as before
1ac0b4c   09 00 80 12   mov  w9, #-1
1ac0b50   69 4e 04 b9   str  w9, [x19, #0x44c]         invalid lap: make the session valid again
1ac0b54   18 00 00 14   b    clear                     and discard this lap (clear, restart)
valid:
1ac0b58   f5 0f 1f f8   str  x21, [sp, #-0x10]!        save x21 (the develified code uses it after)
1ac0b5c   e0 03 13 aa   mov  x0, x19                   x0 = lap-timing object
1ac0b60   97 b6 d5 97   bl   0x102e5bc                 w0 = lap time just recorded (ms)
1ac0b64   f5 03 00 2a   mov  w21, w0                   keep it
1ac0b68   68 82 5d f8   ldur x8, [x19, #-0x28]         x8 = game = [TimeTrialMode+0x188]
1ac0b6c   09 74 82 52   mov  w9, #0x13a0
1ac0b70   29 00 a0 72   movk w9, #0x1, lsl #16         w9 = 0x113a0
1ac0b74   01 69 69 f8   ldr  x1, [x8, x9]              x1 = current event = [game+0x113a0]
1ac0b78   81 01 00 b4   cbz  x1, finish                no event -> finish normally
1ac0b7c   00 e1 11 91   add  x0, x8, #0x478
1ac0b80   38 b4 e9 97   bl   0x152dc60                 x0 = records table (game+0x478+0x9f0)
1ac0b84   f7 ea bb 97   bl   0x9bb760                  x0 = this event's record, or 0
1ac0b88   00 01 00 b4   cbz  x0, finish                no record -> finish normally
1ac0b8c   09 08 40 b9   ldr  w9, [x0, #0x8]            w9 = stored best (ms)
1ac0b90   3f 01 00 71   cmp  w9, #0x0
1ac0b94   ad 00 00 54   b.le finish                    no best yet -> finish normally
1ac0b98   bf 02 09 6b   cmp  w21, w9
1ac0b9c   6b 00 00 54   b.lt finish                    lap faster than best -> finish
1ac0ba0   f5 07 41 f8   ldr  x21, [sp], #0x10          restore x21
1ac0ba4   04 00 00 14   b    clear                     not a best: clear, then restart
finish:
1ac0ba8   f5 07 41 f8   ldr  x21, [sp], #0x10          restore x21
1ac0bac   60 32 40 f9   ldr  x0, [x19, #0x60]          the instruction the hook replaced
1ac0bb0   c2 b7 d5 17   b    0x102eab8                 back into the develified finish
clear:
1ac0bb4   68 ee 40 f9   ldr  x8, [x19, #0x1d8]         x8 = player recorder = [TT+0x318+0x70]
1ac0bb8   68 01 00 b4   cbz  x8, restart
1ac0bbc   08 09 40 f9   ldr  x8, [x8, #0x10]           x8 = its recording
1ac0bc0   28 01 00 b4   cbz  x8, restart
1ac0bc4   08 5d 40 91   add  x8, x8, #0x17, lsl #12
1ac0bc8   08 21 1c 91   add  x8, x8, #0x708            x8 = &node-time vector (recording+0x17708)
1ac0bcc   09 29 40 a9   ldp  x9, x10, [x8]             begin, end
1ac0bd0   0b 00 80 12   mov  w11, #-1
loop:
1ac0bd4   3f 01 0a eb   cmp  x9, x10
1ac0bd8   62 00 00 54   b.hs restart
1ac0bdc   2b 45 00 b8   str  w11, [x9], #4             times[node] = -1 (empty)
1ac0be0   fd ff ff 17   b    loop
restart:
1ac0be4   c9 b7 d5 17   b    0x102eb08                 start a new timed lap
```

Why the validity check exists (new in v4, issue #6): `TimeTrialMode+0x5fc`
says whether the session still counts: `-1` valid, `0` off track, `2` too
much damage. It is set to `-1` when the timed lap starts (`0x1043384`) and
written only by two `TimeTrialMode` handlers, each acting only while the
timed lap runs and the field is still `-1`:

| Handler | Sets | When |
|---|---|---|
| `0x1041a74` | `0` | Off track, when `TimeTrialMode+0x5f8` is 1 (invalidate). If it is 2 the game gives a time penalty instead (`+0x614` `TT_OffTrackPenaltyMs` default 4000, `+0x618` `TT_OffTrackContinuousPenaltyMs` 2000, `+0x620` `TT_OffTrackPenaltyIntervalMs` 2000) and the field stays `-1` |
| `0x1041f90` | `2` | Damage (float compare at `0x104204c`; the threshold value was not traced) |

Both also log telemetry ("Disqualified": "Off Track" / "Damage") and show
"OFF TRACK" / "INVALID LAP" on the HUD for 10 s (`0xf56948`, 10000 ms). The
finish handler `0x1043b64` reads the field at `0x1043c4c`, `0x10441d4`,
`0x1044abc` and `0x10457ac` and skips saving the time when it isn't `-1`:
that is the "Time not recorded" result. Nothing resets it between laps, so
up to v3 one invalid lap voided every later lap. v4 checks it before
anything else; an invalid lap is treated like a slower one (clear, restart)
and the field goes back to `-1` for the next lap.

Why `clear` exists (v3): the recorder only writes a node's time while
it is still `-1`, and nothing else empties them between laps. Without it, a
best set after restarted laps was saved with the first lap's node times and
the live delta compared against that slower lap. Full analysis:
[time-trial-delta-details.md](time-trial-delta-details.md) section 6.

v3 (md5 `93371f159d061aabaed0b2804fce895e` alone, never tested in game) was
the routine from `valid:` on, without the six validity instructions, at
`0x1ac0b40`–`0x1ac0bcf`. `check` reports a v3 library as "old v3 cave".

v2 (tested 2026-10-07, md5 `c610a868dab935c60ea6c3dd70ed5e28` alone) was the
v3 routine without `clear`: `1ac0b8c` was `df b7 d5 17` `b 0x102eb08` and
the routine ended at `1ac0b9b`. `check` reports a v2 library as "old v2 cave".

In v2–v4 every path restores the stack and `x21` before leaving (v5: see
its section above). `x19`, `x20` and the
other registers the develified code uses after `0x102eab8` / `0x102eb08` are left
untouched (`x0`, `x1`, `x8`, `x9` and the call-clobbered registers are free
there: the develified code sets `x0` itself and doesn't read the others).

## 2. Develified code around the change (unchanged, for reference)

The lap-timing tick, `0x102ea04`. Its only caller is `TimeTrialMode` at
`0x1043444`, so this code runs only in Time Trial. `x19` is the lap-timing
object, which is `TimeTrialMode + 0x1b0`.

```
102ea74  tbz  w0, #0, 0x102ead4        ; not on the finish line this frame
102ea78  ldr  w8, [x19, #0x154]        ; w8 = crossings so far
102ea7c  ldr  w9, [x19, #0x98]
102ea80  add  w10, w8, #1
102ea84  str  w10, [x19, #0x154]       ; count this crossing
102ea88  cbz  w9, 0x102eb08            ; timed lap not running yet -> start it
102ea8c  tbnz w8, #31, 0x102eb50       ; <- patched by 2..17/unlimited/reset
102ea90  ldr  w1, [x19, #0x150]        ; \
102ea94  mov  x0, x20                  ;  |
102ea98  bl   0x102d5ec                ;  | record the lap time
102ea9c..102eab0  bl 0x102dc10 / bl 0x102dd6c   ; /
102eab4  ldr  x0, [x19, #0x60]         ; <- patched by best (hook)
102eab8  mov  w8, #2
102eabc  str  w8, [x19]                ; state 2 = finished
102eac0..102ead0                       ; notify listener, then return
...
102eb08  ldrb w8, [x19, #0x15c]        ; "start a new timed lap":
...                                    ;   reset the lap clock (0x102da60),
102eb4c  str  wzr, [x19, #0x154]       ;   crossings = 0
102eb50  ...                           ; common exit
```

Once the timing object's state is 2 (`0x102e5d4` checks this),
`TimeTrialMode`'s own tick (`0x10432bc`, state field `+0x180`) moves to
state 3 and calls the finish handler `0x1043b64`. That handler shows the
results and saves the time. The `best` variant reaches it the develified way.

## 3. Game functions the patch calls or jumps to

All are develified and unmodified.

| Address | What it is | Used by |
|---|---|---|
| `0x102e5bc` | Lap-timing: current lap time in ms (`[obj+0xc0]`, or a helper if flag `+0x9c` is set) | `best` routine |
| `0x152dc60` | `add x0, x0, #0x9f0; ret`: records table inside `game+0x478` | `best` routine |
| `0x9bb760` | Tree lookup by event id (`[event]`); returns `node+0x28` or 0 | `best` routine |
| `0x102eb08` | Develified "start timed lap" path inside the tick | `reset`, `best` |
| `0x102eab8` | Develified "mark finished" path inside the tick | `best` |
| `0x102eb50` | Develified common exit of the tick (target of the original branch) | all count variants |

The `best` lookup copies the one the finish handler itself uses at
`0x1043c8c`–`0x1043ca8`:

```
1043c8c  ldr  x8, [x19, #0x188]        ; game
1043c90  add  x0, x8, #0x478
1043c94  bl   0x152dc60
1043c98  mov  x1, x24                  ; event
1043c9c  bl   0x9bb760                 ; record
1043ca0  bl   0x9b9d5c                 ; ldr w0, [x0, #8]  -> stored best
1043ca8  str  w0, [x19, #0x5e0]        ; used by the results screen
```

The routine reads `[record+8]` directly instead of calling `0x9b9d5c`,
because that function is exactly that one load. It also adds the null checks
the handler doesn't need.

## 4. Fields read and written

| Field | Meaning |
|---|---|
| `TimeTrialMode+0x188` (= timing `-0x28`) | pointer to the game object |
| `game+0x113a0` | current event |
| `game+0x478` | records manager |
| `record+0x8` | stored best lap for that event, ms |
| `timing+0x60` | listener pointer (develified code; reloaded by the routine before returning) |
| `timing+0x154` | crossing counter (read by the develified `w8` load) |
| `TimeTrialMode+0x5fc` (= timing `+0x44c`) | session validity; v4 reads it and writes `-1` after an invalid lap |
| recording `+0x17708` | node-time vector; v3 and v4 write `-1` to every slot on restart |

## 5. Tried and not used

The game mode lap getter and the race lap count (section 0). Both had no
effect in game and the tool writes neither. Details in
`analysis/libRealRacing3.so.md`.

## 6. The tool: `tools/rr3_tt_laps.py`

| Name | Role |
|---|---|
| `SITE`, `DEVELIFIED` | `0x102ea8c` and its develified word `0x37f80628` |
| `RESTART` | `0x1400001f` = `b 0x102eb08` (`reset`) |
| `HOOK`, `HOOK_DEVELIFIED`, `HOOK_CODE` | `0x102eab4`, `0xf9403260`, `0x142a4823` = `b 0x1ac0b40` (`best`) |
| `CAVE`, `CAVE_CODE` | `0x1ac0b40` and the 164 routine bytes listed in section 1 (v5) |
| `CAVE_CODE_V4` | the 168-byte v4 routine (`--best-version 4`) |
| `BEST`, `BEST_LATEST`, `CAVE_LEN` | caves by version (latest 5); `state()` checks `CAVE_LEN` = 168 bytes, so a shorter cave must be followed by zeros |
| `CAVE_CODE_V3` | the 144-byte v3 routine, only so `check` can recognise it |
| `CAVE_CODE_V2` | the 92-byte v2 routine, only so `check` can recognise it |
| `LAPS` | option → bit k (`2`:0, `3`:1, `5`:2, `9`:3, `17`:4, `unlimited`:30) |
| `load()` | reads the library, gunzipping if needed |
| `insn(bit)` | builds `tbz w8, #bit, 0x102eb50` from the develified word |
| `state()` | identifies develified / each variant by checking all three locations |
| `main()` | `check` prints the state. `patch` refuses anything but develified bytes at its sites, then writes the chosen variant |

Building the `best` variant (v5) from the develified library gives md5
`d4eae71ef35ef963f93b5c2c16d67ada` (not tested in game yet); v4 gave
`f75bfb82c309c37a6874a742489fc094`. v3 gave `93371f159d061aabaed0b2804fce895e`
and v2 `c610a868dab935c60ea6c3dd70ed5e28`, the build tested in game on
2026-10-07. v4 is confirmed in game (b30, 2026-10-20: off-track laps,
slower or faster, restart; the next valid faster lap finishes and is
saved). v3 alone was never tested; its node-time clear is part of v4.

The cave is assembled with `llvm-mc -triple=aarch64` and linked with
`ld.lld --section-start=.text=0x1ac0b40` plus `--defsym` for the five game
addresses; the same method reproduces the v3 bytes exactly.

## 7. md5 of every variant

Built from the develified library with `tools/rr3_tt_laps.py patch DEVELIFIED OUT --laps X`
(reproduced 2026-10-12):

| `--laps` | md5 | Tested in game (2026-10-07) | Ready-made (project files `patched/`) |
|---|---|---|---|
| `2` | `c23c8ee2055d75e153ceab20ef881530` | no | |
| `3` | `b616b0c430c640031263d0cc13ba978c` | no | |
| `5` | `024a4775586b78467fa9e5fba37c5b06` | no | |
| `9` | `a2b21a9a0e764b9323448c4aff2d6999` | yes: laps continue, timer counts from lap 1 | `tt-9-laps` |
| `17` | `8dc21e7123b7c28faf2f472b61354f4f` | no | |
| `unlimited` | `1ad832cdea453eff761f94d914d3ddb9` | no | `tt-unlimited-laps` |
| `reset` | `d11c1ffab347f224058730c5b312da53` | yes: timer restarts each lap | `tt-reset-laps` |
| `best` (v5, current) | `d4eae71ef35ef963f93b5c2c16d67ada` | no | |
| `best` (v4) | `f75bfb82c309c37a6874a742489fc094` | yes (b30, 2026-10-20) | |
| `best` (v3) | `93371f159d061aabaed0b2804fce895e` | no | |
| `best` (v2) | `c610a868dab935c60ea6c3dd70ed5e28` | yes: slower lap continues, new best finishes and is saved | `tt-until-best-v2` |

The first `best` build read the game pointer at `x19+0x338` instead of
`x19-0x28` and crashed on the first lap; `tt-until-best-v2` is the fixed
build. Other patches can be stacked on top of `best`; see
[patched-library-details.md](patched-library-details.md).

## 8. Known limits

- Leaving from the pause menu saves nothing; only a finished session is
  saved, and with `best` a session finishes only on a new best (or on the
  first lap when the event has no stored best).
- No stored best: the first lap finishes the session (confirmed in game
  2026-10-12, issue #7).
- Up to v3, an off-track (invalid) lap invalidated the whole session, not
  only that lap. A later lap that beat the best still finished the event, but
  Results showed "Time not recorded", so nothing was saved (confirmed in game
  2026-10-12, issue #6). v4 restarts the invalid lap instead (section 1);
  not tested in game yet.
- v4 with no stored best finishes on the first *valid* lap, not the first lap.
- v4, untested edge cases: an off-track that starts just before the line may
  be flagged on the old lap only, so the new lap starts valid; a damage
  invalidation can happen again on the next lap, since the car's damage
  stays.
- Up to v4, Watch Replay of a ghost slower than your own best for that
  event looped instead of ending after one lap (issue #5). v5 finishes a
  replay at once (section 1); not tested in game yet.
- Long sessions: about 25 laps at Brands Hatch (Aston Martin Vantage V12,
  ELITE > All Out Attack Time Trial) ran with no performance problems, so no
  lap limit or slowdown was seen (2026-10-12, issue #9).
