# Time Trial: no drive point ("energy") cost (summary)

Every Time Trial start costs drive points (the energy bar) unless the car is
VIP. This library patch makes every event cost 0, so any car starts a Time
Trial the way a VIP car does. Your drive point balance is not changed.
Confirmed in game. Detailed version:
[details/time-trial-drive-points-details.md](details/time-trial-drive-points-details.md) (every detailed doc is in [`details/`](details/)).

> **Mali GPU variant only.** Made on the `libRealRacing3.so` of the latest
> `develified.apk` in the
> [Project Real Resurrection Discord](https://discord.com/invite/project-resurrection-official-server-1482888689854971997).
> The tool refuses any library it doesn't recognise.

> **Project Real Resurrection.** Part of Project Real Resurrection's work on Real
> Racing 3. Not affiliated with, endorsed or supported by Electronic Arts.

Alternative without an APK change: make the car VIP in your save
([cars-and-vip.md](cars-and-vip.md)).

## Steps

1. Easiest: use the ready-made combined build, see
   [patched-library.md](patched-library.md).
2. Or patch a library yourself (stock or already patched):
   ```sh
   python3 tools/rr3_drive_cost.py patch IN libRealRacing3.so
   python3 tools/rr3_drive_cost.py check libRealRacing3.so
   ```
3. Put it in the APK and install: [installing.md](installing.md).

---

Detailed version: [details/time-trial-drive-points-details.md](details/time-trial-drive-points-details.md). Every detailed doc is in
[`details/`](details/).
