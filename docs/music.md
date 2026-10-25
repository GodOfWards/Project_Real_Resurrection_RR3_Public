# Music (summary)

> **Project Real Resurrection.** Part of Project Real Resurrection's work on
> Real Racing 3. Not affiliated with, endorsed or supported by Electronic Arts.

Research only: **nothing is patched and nothing here was tested in game.**
Based on the stock `libRealRacing3.so` from the latest `develified.apk`
(Mali GPU variant, RR3 14.0.1, md5 `0e8cc145c5a8b5d9e8ee9a4cb9483793`) and
the game data of one phone. Detailed version:
[details/music-details.md](details/music-details.md). Issue #37.

## How the music works

- The game uses **FMOD** and streams **plain MP3 files** from
  `files/.depot/audio/music/` (18 files). No own format, no playlist file.
- **Menus and screens:** each screen's song name is hardcoded in the lib:
  `Menu_Music.mp3` (main menus), `Garage_Music.mp3`, `LoadingScreen.mp3`,
  `IntroLogos.mp3`, `IntroCinematic.mp3`.
- **Races:** each track file (`files/.depot/Tracks/data/*.bin.nct`, one per
  track and time of day) names **three songs**. When a race starts the game
  shuffles the three and plays them in a row. If all three are empty, the
  music stops.
- 166 of the 167 track files name three songs; only the menu backdrop
  scene (`renderscene-rs-noon-138`) has none. The full list is
  [`analysis/track-music.csv`](../analysis/track-music.csv).
- The three **Formula E** songs are used only on Hong Kong, New York (old
  and 2021), Berlin Formula E and Red Bull Ring South (afternoon and morning
  only; South noon uses Ryan Kurt songs). Every other track uses the 11
  Ryan Kurt songs.

## Changing the music (untested)

| Want | How | Status |
|---|---|---|
| Replace a song everywhere it plays | Put your MP3 in `files/.depot/audio/music/` under the same file name | Untested |
| Change which songs one track plays | Edit the three names in that track's `.bin.nct` (decrypt with `tools/rr3_nct.py`) | Untested; the game may check track files against `Tracks/ttk.dat.nct` checksums |

Back up the original files first. A game data update may restore them.
