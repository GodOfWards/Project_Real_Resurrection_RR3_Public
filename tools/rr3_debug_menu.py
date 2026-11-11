#!/usr/bin/env python3
"""Open EA's built-in debug menu (MainMenuCheatScreen) in libRealRacing3.so
(v14.0.1, arm64, develified build), with AI Skill, the Debug Race Selector
toggle and Time > Override Server Time kept between game starts.
Guides: docs/debug-menu.md (full menu), docs/ai-difficulty.md (--limited).

Two menus:
  full       (default) every category but Sales. For testers and the team.
  --limited  for public builds: only Debug Race Selector, AI, six
             Character entries, Web Browser|PRR Website, the Time submenu,
             the whole Time Trials menu, five Car entries and Party Play
             (trim v7: Unlock Everything and Unlock Next Series in a blue
             Character > Unlock submenu, Give driver levels and Clear money
             & gold plain entries, Car keeps Toggle VIP; a "PRR|" category
             kept for our own entries), so players can't reach the other
             entries (Cloudcell, Test Crash, Own All Cars, Give money,
             Remove Car, ...). v1 confirmed in game (b18, 2026-10-13), v2
             confirmed in game (b47-beta, 2026-11-02); v3 to v7 not tested
             in game.
Both keep AI Skill, Debug Race Selector ON/OFF and Override Server Time in
files/doc/debug_menu_settings.dat (part `settings`),
turn the game's skill recalculation off (part `noskillcalc`), take Hot
Laps and Online Multiplayer Tournament out of the Debug Race Selector (part
`modes`), keep the menu closed in OMP, LTS (WTT, TTC) and Time Trial races
(part `menu` v2) and remove the pause menu's Fix Physics Steps (part
`nophysfix`) and Win (part `nowin`).

How the menu opens: the release lib still contains the developer menu (317
entries, labels built by the static initializer at 0xe19598, handlers
registered by 0xe1d8bc). MainMenuManager creates it at startup (0x14c0244)
and keeps it at manager+0x420. A GuiCheatProtector widget (main menu, pause
menu) opens it: three quick taps near a screen corner, then the Java text
box asks for the password "Ironmint". Every step first checks a "cheats
allowed" byte (+0x561 of the game settings object) that only the eSports demo
mode sets, so normally nothing happens.

The AI category (SetupAiCheats, 0xe29260) has four buttons:
  AI Skill        cycles a global override (0x1f815f0, -1 at every launch)
                  that every AI car reads: None (-1, normal skill) > Dead
                  (-2, AI cars don't drive) > Easy (0) > Hard (100) > None.
  Current Skill   the skill stored for the current series (a map at game
                  state +0x478, keyed by series); a tap adds 10 (0 ... 100,
                  then back to 0; handler 0xa6c790).
  Set skill (N)   sets that stored skill to N = the menu's top slider
                  (widget id 999, menu+0x534) * 100, 0-100 (handler
                  0xa6c8b8). The slider is created by the menu builder
                  itself (0xe274f8), so `trim` keeps it.
  Show Skill in Name  shows each opponent's skill next to its name.

Parts (default: all but `trim`; --limited adds `trim`; --parts picks some):

  menu  (called `open` in the old rr3_ai_menu.py; `open` still works) three
        quick taps in any screen corner open the menu (Tom, 2026-10-28):
    0x10e8dfc  `ldrb w8, [x0, #0x561]` -> `mov w8, #1`: corner taps count.
    0x10e8ab4  skip the Java text box and the password, jump to the
               "already unlocked" path (0x10e8ba4) that opens the menu.
    Versions (`check` knows both, `patch` writes the latest):
      v2  (issue #635, anti-cheat, Tom 2026-11-10) 0x10e8dfc is `bl
          0xfecb10` (menu_gate, tools/asm/rr3_debug_menu_gate.s, 41 words,
          this tool's slice 0xfecb10..0xfecbb4 of the dead benchmark-table
          function, cave 0xfec9c4..0xfede6c): the taps do nothing during an
          OMP match (OMP state 3..8), an online multiplayer race (mode 24,
          Race Selector P2P too), any LTS race (event stream type 7: WTT,
          TTC, community, Seasons rounds) and any Time Trial (mode 18)
          except the Race Selector's (event 18130). The same handler serves
          the pause menu, whose tweak panel (Win, Player AI, Lose, Restart, Fix
          Physics Steps, ...) the third tap shows, so it is blocked too.
          Menus (no game mode), career races and Race Selector races keep
          the menu. Not tested in game. `--menu-version 1` writes v1.
      v1  0x10e8dfc `mov w8, #1`: the taps count everywhere.

  nowin  (#606 A8, Tom 2026-11-11, every build) the pause tweak panel's
        "Win" button finished the race at once (any race the panel opens in;
        menu v2 already kept it closed in online, LTS and Time Trial races).
        Its action, the member function 0x14e889c (only reference: GOT
        0x1f7aa00, bound by CreatePauseTweaksCheatButtons at 0x14dfb60), now
        returns at once, so the button does nothing:
    0x14e889c  `stp x29, x30, [sp, #-0x20]!` -> `ret`. Not tested in game.

  nophysfix  (issue #635, #613, every build) the pause tweak panel's "Fix
        Physics Steps" (one 16 ms physics step per frame: slow motion below
        62.5 FPS; its flag 0x1f973d8 stayed on until the game restarted)
        does nothing:
    0x14e935c  toggle body `adrp x8, 0x1f6f000` -> `ret`. Not tested in game.

  trim  the menu shows only the entries below, as in the full debug menu;
        every other entry gets no button.
    Versions (`check` knows all seven, `patch` writes the latest):
      v7  (issue #590, Tom 2026-11-09) as v6, plus three changes:
          Character keeps Clear money & gold (entry 27, full label
          "Character|Clear money & gold"; one tap sets R$ and gold to 0),
          the whole Time Trials menu ("Time Trials|" instead of "Time
          Trials|WTT|": static 53-56 EnableLiveDON, Force Version Reset,
          Force Season Reset, Clear Formula E Signup, plus TTC added by
          0xe2ea74) and Car keeps Toggle VIP again (75, as in v2). Six
          static entries more than v6: 29, or 31 with settings v5's two
          PRR entries (Offline, Pin date). Same code and slice; 97 of the
          slice's 128 words. Not tested in game. `--trim-version 6` writes v6.
      v6  (issue #215, Tom 2026-11-07) as v5, but Character also keeps
          Give driver levels (entry 22, full label "Character|Give driver
          levels", a plain entry: one driver level per tap) and Car drops
          Remove Upgrades From All Cars (68), Remove Car (72) and Remove All
          Cars (73): Car keeps Damage, Degrade, Repair Car and Remove
          Upgrades From Car (64, 65, 66, 69). 23 static entries kept (v5:
          25). Same code and slice; 87 of the slice's 128 words. Not tested
          in game. `--trim-version 5` writes v5.
      v5  (issue #215, Tom 2026-11-06) as v4, plus two prefixes: "Party
          Play|" (the ten static Party Play entries 256-265: Force 1/2/3/4/
          Zero/Num/Max Players, Force AI Drivers, Enable AI Opponents, AI
          Opponent Count; #126/#145) and "PRR|", a category kept for
          Project Real Resurrection's own entries (offline switch #309, ...),
          so a new entry of ours needs no new trim version. No label starts
          with "PRR|" yet. Same code and slice; 97 of the slice's 128 words.
          Not tested in game. `--trim-version 4` writes v4.
      v4  (issue #318) as v3, plus Unlock Everything and Unlock Next Series
          move into a blue Character > Unlock submenu, so one stray tap
          can't apply them: in each label the space after "Unlock" becomes
          "|" (.rodata 0x473908, 0x4631b8; same length). Filter prefix
          "Character|Unlock|". Not tested in game. `--trim-version 3` writes v3.
      v3  (issue #215) as v2, same code and slice, but for a "legit" run
          Character keeps four full labels only: Unlock Everything, Unlock
          Next Series, Save game, Validate user data (Unlock + Own
          Everything, Own All Cars, Give XP / levels / money / gold, Clear
          local save, Wallet, Early Access, ... stay hidden), and
          Car|Toggle VIP is dropped (seven Car entries). Not tested in game.
          `--trim-version 2` writes v2.
      v2  (issue #225) keeps labels starting with "AI|", "Character|",
          "Debug Race Selector", "Web Browser|PRR" (rr3_prr_login.py),
          "Time|" (the whole Time submenu: Override Server Time, Force
          Unreliable, Add/Remove Days/Hours/Minutes/Seconds, Reset),
          "Time Trials|WTT|" (WTT only) and eight full Car labels: Damage
          Car, Degrade Car, Repair Car, Remove Upgrades From All Cars,
          Remove Upgrades From Car, Remove Car, Remove All Cars, Toggle VIP.
          The filter is at 0x1584104, this tool's slice 0x1584104..0x1584304
          of the dead physics-state compare (cave 0x1583704..0x15846a8), so
          v2 doesn't need `nosales`; 0xe2f40c stays develified. The menu
          builder's calls 0xe27878 (Time, 0xe2b174) and 0xe278b0 (Time Trials
          TTC/WTT, 0xe2ea74) run again; the filter hides what they add but
          Time| and Time Trials|WTT|. The Car and Override Server Time /
          Force Unreliable entries are static entries. Not tested in game.
      v1  AI|, Character| and Debug Race Selector only, filter at 0xe2f40c
          in SetupSaleCheats (b18 and later limited builds).
          `--trim-version 1` writes it. The text below is v1.
    0xe266d8   first instruction of the add-entry function (AddCheat: menu,
               label, handler; returns the entry's index) -> `b 0xe2f40c`
               (filter, tools/asm/rr3_debug_menu_filter.s). Labels starting with
               "AI|", "Character|" or "Debug Race Selector" are added as
               usual; others only take their index (menu+0x4e8 still goes
               up, so all indexes match the full menu) and get no button.
               Their slot in the button list (menu+0x450) stays empty, which
               every reader of it checks. The 317 static entries (0xe1d8bc)
               and the handler wiring (0xe1db64) run unchanged.
    0xe27838.. in the menu builder (0xe27700), the Setup*Cheats calls with no
               AI or Character entry (Car Market, Rec Packs, Championship,
               Tutorial, Metagame, Balance Pass, Time, Championships,
               Cloudcell, Daily Rewards, Time Trials, OMP, LTS, MTX)
               become nop, and so does the macro buttons call (0xe278cc):
               RUN MACRO replays entries by index from cheat_macro.bin.
               Still called: 0xe27830 (Character|Early Access|Streams, also
               Career groups, hidden), 0xe27848 (Character|Wallet),
               SetupAiCheats (0xe27860) and 0xe278a0 (Character|Clear
               purchased packs, plus other hidden entries). Needs `nosales`
               (the filter code sits in SetupSaleCheats).

  nosales  the menu builder no longer calls SetupSaleCheats (0xe2f2b4), so
        its code is free for the new code of `settings` and `trim`. Only the
        Sales category (store sale cheats, no use offline) disappears.
    0xe278c0   `bl 0xe2f2b4` -> nop. It is the only branch into that code and
               no pointer or relocation points into it (checked on b10).
    `--restore` of `nosales` is refused while any byte of SetupSaleCheats
    (0xe2f2b4..0xe2f70c) is not back to develified: the menu builder would run our code
    (`settings`, `trim`, rr3_username.py) as SetupSaleCheats. Restore those
    first.

  race  turning Debug Race Selector ON shows the white Sigma button on
        the career hub and the selector screen stays open:
    0xd9bfe8, 0xdb6e20, 0xd983b0  `bl 0x10e87c4` (cheats allowed?) -> `mov w0, #1`.

  settings  AI Skill, the Debug Race Selector toggle and Time > Override
        Server Time are kept between game starts in our own file,
        files/doc/debug_menu_settings.dat (next to character.2.dat), so the
        game's saves are never touched. 20 bytes, little-endian: magic
        "RRDM", version 3, AI Skill override, Race Selector (0/1), Override
        Server Time (0/1). Override Server Time is YES unless the file
        holds NO (issue #195: no file or a v1/v2 file gives YES). A saved
        Dead loads as None (v3, issue #168): Dead also stops other players'
        cars in Online Multiplayer, so it lasts one game start only. New
        code from tools/asm/rr3_debug_menu_settings.s, placed in
        SetupSaleCheats (0xe2f2b4 and 0xe2f6cc), which `nosales` leaves
        unreachable; needs `nosales` (works with or without `trim`). The
        `trim` filter code follows it at 0xe2f40c.
    0xbd3b74   AI Skill setter (0xbd3b68), `ret` -> `b 0xe2f2b4`
               (settings_save): after the setter's own store, write the file
               (fopen "w" / fwrite / fclose; path = doc folder getter
               0x12a57f0 + name, via snprintf).
    0xa685e8   Debug Race Selector handler (0xa685c4, flag 0x1f9d460), menu
               refresh `bl 0xe32728` -> `bl 0xe2f6cc` (toggle_saved): write
               the file, then the refresh.
    0xa6885c   Override Server Time handler (0xa68848, flag 0x1fb5520), tail
               call `b 0xe32728` -> `b 0xe2f6cc` (toggle_saved).
    0x12f1c0c  last `ret` of the profile load/save function 0x12f1130 ->
               `b 0xe2f2fc` (settings_load): read the file if it exists and
               has the magic, set AI Skill, the toggle (if the file has it)
               and Override Server Time (YES if the file lacks it), return 1
               as before. Only used as a "storage is ready" moment; the
               profile itself is not read or changed.
    Versions (`check` knows all five, `patch` writes the latest):
      v5  (issue #309) as v4, plus two Project Real Resurrection entries in
          the PRR category, kept in a 28-byte file (version 4; +20 flags,
          +24 pinned time):
            PRR|Offline (restart):  static entry 196 (was "System|GameText
              Errors: "); its .bss byte (GOT 0x1f6e5e0) is the offline flag
              tools/rr3_offline.py reads. Handler end 0xa6a930 -> b 0xe2f6cc
              (toggle_saved); its game reader 0x106ca1c -> mov w8, #0.
            PRR|Pin date (restart): static entry 186 (was "Crew|Disp Random
              Timer: "); byte GOT 0x1f6e6b8. Handler `ret` 0xa7116c -> b
              0xfecac4 (pin_saved: turning it on saves the game's time,
              time(NULL) + Server Time Offset when Override Server Time is
              on, then the menu refresh); game reader 0x14ff74c -> mov w8, #0.
          At start, Offline and Pin date both on: Override Server Time YES
          and Server Time Offset = pinned time - time(NULL), so the game's
          clock (0x14163f4) starts at the pinned time every start. The
          pinned time lives in the file only; a save keeps it unless Pin
          date was just turned on. Code: 0xe2f2b4..0xe2f478 (also trim v1's
          slice: refused with trim v1), 0xe2f6cc, pin_saved 0xfecac4 and
          open_file 0x1bac904. Load hook 0x12f1c0c -> b 0xe2f320. Not
          tested in game. `--settings-version 4` writes v4.
      v4  as v3, plus Override Server Time (YES unless saved NO); 20-byte
          file (version 3). Hooks 0xbd3b74 and 0xa685e8 instead of v1-v3's
          0xbd3b68 (cave_set) and 0xa685e4 (race_toggle). Not tested in game.
      v3  as v2, but a saved AI Skill Dead (-2) loads as None (-1). Same
          file (version 2). b39..b42. `--settings-version 3` writes it.
      v2  AI Skill + Race Selector, 16-byte file; also reads a v1 file
          (toggle OFF). b35..b37. `--settings-version 2` writes it.
      v1  AI Skill only, 12-byte file (b23). `--settings-version 1` writes
          it, for testing. v1 reads the first 12 bytes of a v2 file.

  noskillcalc  the game's skill recalculation after each race starts off, so
        a skill set with Set skill stays (Tom's decision 2026-10-13: always
        off in AI builds). Skill manager constructor 0x133869c:
    0x13386cc  `mov w11, #0x101` -> `mov w11, #0x1` (strh at 0x13386f0 then
               leaves byte +0x5, "Skill Calculation", at 0; 0xf4c338 skips the
               update when it is 0).

  modes  (issue #40, v1, every build) the Debug Race Selector no longer
        offers Hot Laps (mode 11, crashes on the loading screen) or Online
        Multiplayer Tournament (mode 12): EA removed both modes
        (game_DoSetupGameMode only logs "... Mode No Longer Supported").
        Not tested in game. Both selector UIs read one 31-entry mode table
        (.data VA 0x1f80b20, file 0x1f7eb20) by index:
    file 0x1f7eb50  table slots 12..30: 11 and 12 taken out, the rest moved up,
               16 (Sandbox, the list's first mode) in the two freed slots at the end.
    0x9f6ff0   ImGui "Select Mode:" combo (DebugRaceSelectorUI): loops 29
               entries, not 31.
    0xd98a04, 0xd98a0c, 0xd98a20, 0xd98a28  DebugRaceSelectScreen (the
               screen the Sigma button opens): row vector 29 entries, not 31.
    0xd98a80..0xd98ac0  its fill loop (mode 0..30, entry indexOf(mode)): the
               same 16 instructions reordered, indexOf first, and a mode not
               in the table (indexOf -1) is skipped before any string is
               made. Without this it would write in front of the vector.
    0x9f4e30   the DebugRaceSelect.2.cfg loader's `bl fclose` -> `bl
               0x1bac8f0` (cave, zero padding): a saved mode index >= 29
               (unsigned) becomes 0, then fclose. Start Race launches the
               mode of the saved index, which nothing else checks.

Usage:
  rr3_debug_menu.py check LIB
  rr3_debug_menu.py patch IN OUT [--limited] [--parts menu,nosales,trim,settings,race,noskillcalc,modes,nophysfix,nowin]
                    [--menu-version {1,2}] [--settings-version {1,2,3,4,5}] [--trim-version {1,...,7}] [--restore]
IN may be gzipped; OUT is written uncompressed (or gzipped if it ends in .gz).
The default full menu is build b23's menu; `--limited` is b18's. The older
full menu without persistence (b10, b12; the old rr3_debug_menu.py) is
`--parts menu,race`. To turn a full-menu lib into a limited one: `--parts trim`.
"""
import argparse
import gzip
import hashlib
import struct
import sys

NOP = 0xD503201F
# SetupSaleCheats, where `settings`, `trim` and rr3_username.py put new code,
# and the sha256 of its develified bytes.
SALES_FN = (0xE2F2B4, 0xE2F70C)
SALES_FN_SHA256 = "a05a3e3843493ec57a2aaaa92c63e77dcfe7a8d11a39b385caafcf71514271cd"
# Code caves this tool writes in need these (tables/lib-code-caves.csv,
# checked by rr3_patch_sites.py check); main() refuses the parts without it.
REQUIRES = ["rr3_debug_menu.py nosales"]
# Calls in the menu builder that part "trim" turns into nop: every
# Setup*Cheats with no AI or Character entry, and the macro buttons; develified
# `bl` words. Kept: 0xe27830 (0xe2795c, Character|Early Access|Streams),
# 0xe27848 (0xa76e38, Character|Wallet), 0xe27860 (SetupAiCheats), 0xe278a0
# (0xe2d3b8, Character|Clear purchased packs). The SetupSaleCheats call
# (0xe278c0) is part "nosales".
SKIPPED_CALLS = [
    (0xE27838, 0x9400044F), (0xE27840, 0x940005A3),
    (0xE27850, 0x97F14007), (0xE27858, 0x97F140F0),
    (0xE27868, 0x940009E4), (0xE27870, 0x94000D8B), (0xE27878, 0x94000E3F),
    (0xE27880, 0x940010C5), (0xE27888, 0x94001499), (0xE27890, 0x940014E3),
    (0xE27898, 0x94001675), (0xE278A8, 0x94001B49),
    (0xE278B0, 0x94001C71), (0xE278B8, 0x97F13C6C),
    (0xE278CC, 0x94001F90),  # macro buttons
]

# New code for part "settings": tools/asm/rr3_debug_menu_settings.s (v4), linked
# for 0xe2f2b4 and 0xe2f6cc (build line in that file); v1, v2 and v3 are in git
# history.
# CAVE_DEVELIFIED / GAP_DEVELIFIED = the SetupSaleCheats words they replace.
CAVE_DEVELIFIED = (
    0xD103C3FF, 0xA90A7BFD, 0xF9005BF9, 0xA90C5FF8, 0xA90D57F6, 0xA90E4FF4,
    0x910283FD, 0xD53BD058, 0xF940170A, 0x528C2A6B, 0x52800188, 0x910063E9,
    0x72ACAD8B, 0x528F8E6C, 0x910063E1, 0xAA0003F3, 0xB2400139, 0xF81F83AA,
    0x390063E8, 0xB80193EB, 0x7801D3EC, 0x39007FFF, 0x94002190, 0x394063E8,
    0xA9422BE9, 0xA9007FFF, 0xF9000BFF, 0xD341FD0B, 0x7200011F, 0x9A890174,
    0x91006288, 0x9A8A0335, 0xB100411F, 0x54001E62, 0xF100591F, 0x540000C8,
    0x531F7A88, 0x910003E9, 0x390003E8, 0xB2400136, 0x1400000A, 0x9100A288,
    0x927CED17, 0xAA1703E0, 0x943FA1F7, 0xAA0003F6, 0xB24002E8, 0xA90083F4,
    0xF90003E8, 0xB40000B4, 0xAA1603E0, 0xAA1503E1, 0xAA1403E2, 0x943FA21E,
    0xB0FFB2A1, 0x9123D821, 0x910003E0, 0x52800302, 0x38346ADF, 0x941E87AF,
    0xD0008268, 0xD000826A, 0x9105E108, 0xD10103A9, 0x9107E14A, 0x9100C3F4,
    0x910003E1, 0xD10103A2, 0x9100C3E3, 0xAA1303E0, 0xA93C4FA8, 0xF81E03A9,
    0xF9001BEA, 0xF9002BF4, 0x94000187, 0xF9402BE0, 0xEB00029F, 0x540000A0,
    0xB40000E0, 0xF9400008, 0xF9401508, 0x14000003, 0xF9400008, 0xF9401108,
    0xD63F0100, 0xF85E03A0,
)
CAVE_V1 = (
    0x90008A08, 0xF9465508, 0xB9000100, 0x14000025, 0xA9AD7BFD, 0x910003FD,
    0x9100C3E0, 0x9400003D, 0x9100C3E0, 0xF0FFAFE1, 0x911FF821, 0x943FA280,
    0xB4000320, 0xF9000BE0, 0xAA0003E3, 0x910063E0, 0xD2800021, 0xD2800182,
    0x943FA2E9, 0xF90017E0, 0xF9400BE0, 0x943FA27A, 0xF94017E0, 0xF100301F,
    0x540001A1, 0xB9401BE8, 0x528A4A49, 0x72A9A889, 0x6B09011F, 0x54000101,
    0xB9401FE8, 0x7100051F, 0x540000AB, 0xB94023E9, 0x90008A08, 0xF9465508,
    0xB9000109, 0x52800020, 0xA8D37BFD, 0xD65F03C0, 0xA9AD7BFD, 0x910003FD,
    0x9100C3E0, 0x94000019, 0x9100C3E0, 0xB0FFAEA1, 0x91336821, 0x943FA25C,
    0xB4000240, 0xF9000BE0, 0x528A4A48, 0x72A9A888, 0xB9001BE8, 0x52800028,
    0xB9001FE8, 0x90008A08, 0xF9465508, 0xB9400108, 0xB90023E8, 0xAA0003E3,
    0x910063E0, 0xD2800021, 0xD2800182, 0x943FA274, 0xF9400BE0, 0x943FA24E,
    0xA8D37BFD, 0xD65F03C0, 0xA9BE7BFD, 0x910003FD, 0xF9000BE0, 0x9411D908,
    0xAA0003E3, 0xF9400BE0, 0xD2802001, 0x10000082, 0x943FA913, 0xA8C27BFD,
    0xD65F03C0, 0x65647325, 0x5F677562, 0x756E656D, 0x7465735F, 0x676E6974,
    0x61642E73, 0x00000074,
)
CAVE_V4 = (
    0xA9BC7BFD, 0x910003FD, 0x910063E0, 0x94000038, 0xB0FFAEA1, 0x91336821,
    0x94000041, 0xB4000120, 0xF9000BE0, 0xAA0003E3, 0x910063E0, 0xD2800021,
    0xD2800282, 0x943FA2A6, 0xF9400BE0, 0x943FA280, 0xA8C47BFD, 0xD65F03C0,
    0xA9BC7BFD, 0x910003FD, 0x910063E0, 0x94000026, 0x52800028, 0xB9002BE8,
    0xF0FFAFE1, 0x911FF821, 0x9400002D, 0xB4000120, 0xF9000BE0, 0xAA0003E3,
    0x910063E0, 0xD2800021, 0xD2800282, 0x943FA2DA, 0xF9400BE0, 0x943FA26C,
    0xB9401BE8, 0x18001D8B, 0xB9402BE9, 0x7100013F, 0x1A9F07E9, 0x6B0B011F,
    0x1A9F0529, 0xD00089EA, 0xF9467D48, 0x39000109, 0x54000141, 0x29442FE9,
    0x3100093F, 0x5A9F1129, 0xF9565548, 0xB9000109, 0x7100017F, 0x1A9F07EB,
    0xF94ACD48, 0x3900010B, 0x52800020, 0xA8C47BFD, 0xD65F03C0, 0x58001AC8,
    0xF9000008, 0xD00089E9, 0xF9565528, 0xB9400108, 0xF94ACD2A, 0x3940014A,
    0x29012808, 0xF9467D2A, 0x3940014A, 0xB900100A, 0xD65F03C0, 0xA9AE7BFD,
    0x910003FD, 0xF9000BE1, 0x9411D905, 0xAA0003E3, 0x910083E0, 0xD2802001,
    0x10001782, 0x943FA910, 0x910083E0, 0xF9400BE1, 0x943FA239, 0xA8D27BFD,
    0xD65F03C0,
) + CAVE_DEVELIFIED[85:]                                    # 0xe2f408 stays develified
# v3: AI Skill + Race Selector, a saved Dead loads as None.
CAVE_V3 = (
    0x90008A08, 0xF9465508, 0xB9000100, 0x1400002B, 0xA9BC7BFD, 0x910003FD,
    0xF0FFAFE1, 0x911FF821, 0x94000040, 0xB4000440, 0xF9000BE0, 0xAA0003E3,
    0x910063E0, 0xD2800021, 0xD2800202, 0x943FA2EC, 0xF9001BE0, 0xF9400BE0,
    0x943FA27D, 0xF9401BE0, 0xF100301F, 0x540002C3, 0xB9401BE8, 0x528A4A49,
    0x72A9A889, 0x6B09011F, 0x54000221, 0xB9401FE8, 0x7100051F, 0x540001CB,
    0xB94023E9, 0x3100093F, 0x5A9F1129, 0xF00089EA, 0xF94E5548, 0xB9000109,
    0xF100401F, 0x540000C3, 0xB94027E9, 0x7100013F, 0x1A9F07E9, 0xF942CD48,
    0x39000109, 0x52800020, 0xA8C47BFD, 0xD65F03C0, 0xA9BC7BFD, 0x910003FD,
    0xB0FFAEA1, 0x91336821, 0x94000016, 0xB4000260, 0xF9000BE0, 0xD28A4A48,
    0xF2A9A888, 0xF2C00048, 0xF9000FE8, 0xF00089E9, 0xF94E5528, 0xB9400108,
    0xF942CD29, 0x39400129, 0x290427E8, 0xAA0003E3, 0x910063E0, 0xD2800021,
    0xD2800202, 0x943FA270, 0xF9400BE0, 0x943FA24A, 0xA8C47BFD, 0xD65F03C0,
    0xA9AE7BFD, 0x910003FD, 0xF9000BE1, 0x9411D904, 0xAA0003E3, 0x910083E0,
    0xD2802001, 0x10001762, 0x943FA90F, 0x910083E0, 0xF9400BE1, 0x943FA238,
    0xA8D27BFD, 0xD65F03C0,
)
# v2: as v3, but a saved Dead (-2) loads as Dead.
CAVE_V2 = (
    0x90008A08, 0xF9465508, 0xB9000100, 0x1400002A, 0xA9BC7BFD, 0x910003FD,
    0xF0FFAFE1, 0x911FF821, 0x94000040, 0xB4000420, 0xF9000BE0, 0xAA0003E3,
    0x910063E0, 0xD2800021, 0xD2800202, 0x943FA2EC, 0xF9001BE0, 0xF9400BE0,
    0x943FA27D, 0xF9401BE0, 0xF100301F, 0x540002A3, 0xB9401BE8, 0x528A4A49,
    0x72A9A889, 0x6B09011F, 0x54000201, 0xB9401FE8, 0x7100051F, 0x540001AB,
    0xB94023E9, 0x90008A08, 0xF9465508, 0xB9000109, 0xF100401F, 0x540000E3,
    0xB94027E9, 0x7100013F, 0x1A9F07E9, 0xF00089E8, 0xF942CD08, 0x39000109,
    0x52800020, 0xA8C47BFD, 0xD65F03C0, 0xA9BC7BFD, 0x910003FD, 0xB0FFAEA1,
    0x91336821, 0x94000017, 0xB4000280, 0xF9000BE0, 0xD28A4A48, 0xF2A9A888,
    0xF2C00048, 0xF9000FE8, 0x90008A08, 0xF9465508, 0xB9400108, 0xF00089E9,
    0xF942CD29, 0x39400129, 0x290427E8, 0xAA0003E3, 0x910063E0, 0xD2800021,
    0xD2800202, 0x943FA270, 0xF9400BE0, 0x943FA24A, 0xA8C47BFD, 0xD65F03C0,
    0xA9AE7BFD, 0x910003FD, 0xF9000BE1, 0x9411D904, 0xAA0003E3, 0x910083E0,
    0xD2802001, 0x10001762, 0x943FA90F, 0x910083E0, 0xF9400BE1, 0x943FA238,
    0xA8D27BFD, 0xD65F03C0,
)
# 0xe2f6cc..0xe2f6f8: race_toggle and the path string (v2 and v3);
# 0xe2f6cc..0xe2f700: toggle_saved, the path string and record_head (v4).
GAP_DEVELIFIED = (
    0xA94A7BFD, 0x9103C3FF, 0xD65F03C0, 0xF9400BE0, 0x943FA11D, 0x394063E8,
    0x3607FE48, 0xF94017E0, 0x943FA119, 0xF9401708, 0xF85F83A9, 0xEB09011F,
    0x54FFFE00,
)
GAP_V4 = (
    0xA9BF7BE0, 0x97FFFEF9, 0xA8C17BE0, 0x14000C14, 0x65647325, 0x5F677562,
    0x756E656D, 0x7465735F, 0x676E6974, 0x61642E73, 0x00000074, 0x4D445252,
    0x00000003,
)
GAP_V3 = (
    0x39000109, 0x97FFFF27, 0xAA1303E0, 0x17F0E3C4, 0x65647325, 0x5F677562,
    0x756E656D, 0x7465735F, 0x676E6974, 0x61642E73, 0x00000074,
)
GAP_V2 = (
    0x39000109, 0x97FFFF26, 0xAA1303E0, 0x17F0E3C4, 0x65647325, 0x5F677562,
    0x756E656D, 0x7465735F, 0x676E6974, 0x61642E73, 0x00000074,
)
SETTINGS_HOOKS = [
    (0xBD3B68, (0x90009CE8,), (0x14096DD3,)),               # adrp x8 -> b 0xe2f2b4 (cave_set)
    (0x12F1C0C, (0xD65F03C0,), (0x17ECF5AE,)),              # ret -> b 0xe2f2c4 (settings_load)
]
SETTINGS_HOOKS_V4 = [
    (0xBD3B74, (0xD65F03C0,), (0x14096DD0,)),               # AI Skill setter: ret -> b 0xe2f2b4 (settings_save)
    (0x12F1C0C, (0xD65F03C0,), (0x17ECF5BC,)),              # ret -> b 0xe2f2fc (settings_load)
    (0xA685E8, (0x940F2850,), (0x940F1C39,)),               # race toggle: bl 0xe32728 -> bl 0xe2f6cc (toggle_saved)
    (0xA6885C, (0x140F27B3,), (0x140F1B9C,)),               # server time toggle: b 0xe32728 -> b 0xe2f6cc
]

# Part "settings" v5 (issue #309): tools/asm/rr3_debug_menu_settings.s linked
# for 0xe2f2b4 (113 words, up to 0xe2f478: v5 also uses trim v1's slice, so
# the two can't go together), 0xe2f6cc (13 words), 0xfecac4 (pin_saved, 19
# words, this tool's slice 0xfecac4..0xfecb44 of the dead benchmark-table
# function, cave 0xfec9c4..0xfede6c) and 0x1bac904 (open_file, 15 words, the zero padding
# after the `modes` clamp, cave 0x1bac8f0). File: 28 bytes, version 4 (+20
# flags: bit 0 Offline, bit 1 Pin date; +24 pinned time).
CAVE_V5_DEVELIFIED = CAVE_DEVELIFIED + (                   # = FILTER_DEVELIFIED[:27] (checked below)
    0xD10103A8, 0xEB00011F, 0x540000A0, 0xB40000E0, 0xF9400008, 0xF9401508,
    0x14000003, 0xF9400008, 0xF9401108, 0xD63F0100, 0x394003E8, 0x36000068,
    0xF9400BE0, 0x943FA1C4, 0x394063E8, 0xA9422BE9, 0xA9007FFF, 0xF9000BFF,
    0xD341FD0B, 0x7200011F, 0x9A890174, 0x91006288, 0x9A8A0335, 0xB100411F,
    0x540014C2, 0xF100591F, 0x540000C8,
)
CAVE_V5 = (
    0x52800001, 0xA9BC7BFD, 0x910003FD, 0xB90017E1, 0xA901FFFF, 0xA902FFFF,
    0x910063E0, 0x94000059, 0x910063E0, 0x94000046, 0xB94017E1, 0x34000041,
    0xB90033E1, 0xB0FFAEA1, 0x91336821, 0x9435F585, 0xB4000120, 0xF9000BE0,
    0xAA0003E3, 0x910063E0, 0xD2800021, 0xD2800382, 0x943FA29D, 0xF9400BE0,
    0x943FA277, 0xA8C47BFD, 0xD65F03C0, 0xA9BC7BFD, 0x910003FD, 0x910063E0,
    0x94000031, 0x52800028, 0xB9002BE8, 0x2905FFFF, 0x910063E0, 0x9400003D,
    0xB9401BE8, 0x18001D8B, 0xB9402BE9, 0x7100013F, 0x1A9F07E9, 0x6B0B011F,
    0x1A9F0529, 0xD00089EA, 0xF9467D48, 0x39000109, 0x540003C1, 0x29442FE9,
    0x3100093F, 0x5A9F1129, 0xF9565548, 0xB9000109, 0x7100017F, 0x1A9F07EB,
    0xF94ACD48, 0x3900010B, 0x2945AFE9, 0x1200012C, 0x5301052D, 0xF94AF148,
    0x3900010C, 0xF94B5D48, 0x3900010D, 0x6A0D019F, 0x54000180, 0xB90013EB,
    0xD2800000, 0x943FA22C, 0xB94013EB, 0x4B00016B, 0xD00089EA, 0xF94ADD48,
    0xB900010B, 0xF9467D48, 0x52800029, 0x39000109, 0x52800020, 0xA8C47BFD,
    0xD65F03C0, 0x58001848, 0xF9000008, 0xD00089E9, 0xF9565528, 0xB9400108,
    0xF94ACD2A, 0x3940014A, 0x29012808, 0xF9467D2A, 0x3940014A, 0xF94AF128,
    0x39400108, 0xF94B5D2B, 0x3940016B, 0x2A0B0508, 0x2902200A, 0xD65F03C0,
    0xA9BE7BFD, 0x910003FD, 0xF9000BE0, 0xF0FFAFE1, 0x911FF821, 0x9435F52F,
    0xB4000120, 0xF9000FE0, 0xAA0003E3, 0xF9400BE0, 0xD2800021, 0xD2800382,
    0x943FA28F, 0xF9400FE0, 0x943FA221, 0xA8C27BFD, 0xD65F03C0,
)
GAP_V5 = (
    0xA9BF7BE0, 0x97FFFEF9, 0xA8C17BE0, 0x14000C14, 0x65647325, 0x5F677562,
    0x756E656D, 0x7465735F, 0x676E6974, 0x61642E73, 0x00000074, 0x4D445252,
    0x00000004,
)
PIN_AT = 0xFECAC4                                          # pin_saved
PIN_DEVELIFIED = (
    0xA901FFFF, 0xF90017FF, 0xA903FFFF, 0xFD001BE0, 0xB90013E8, 0x9417B565,
    0xB0FF9CE8, 0x3DC21D00, 0xB90043FF, 0x3D800FE0, 0xF94002E8, 0xF94002A9,
    0xEB09011F, 0x54000222, 0xB94013E9, 0x9100830A, 0xB9000109, 0xF9400A89,
    0x3DC00280,
)
PIN_V5 = (
    0xA9BF7BE0, 0xB0007C09, 0xF94B5D28, 0x39400108, 0x52800001, 0x34000168,
    0xD2800000, 0x9438AC64, 0xB0007C09, 0xF9467D28, 0x39400108, 0x34000088,
    0xF94ADD28, 0xB9400108, 0x0B080000, 0x2A0003E1, 0x97F909ED, 0xA8C17BE0,
    0x17F91707,
)
OPEN_AT = 0x1BAC904                                         # open_file
OPEN_V5 = (
    0xA9AE7BFD, 0x910003FD, 0xF9000BE1, 0x97DBE3B8, 0xAA0003E3, 0x910083E0,
    0xD2802001, 0xF0FF9402, 0x911B7042, 0x9409B3C2, 0x910083E0, 0xF9400BE1,
    0x9409ACEB, 0xA8D27BFD, 0xD65F03C0,
)
# The two PRR entries (static entries 196 and 186): new labels in .rodata
# (each read only by the label initializer, 0xe1bb24 and 0xe1b8f4; the same
# length, 24 characters: the initializer copies the old length, so a shorter
# label would keep a 0 inside it and hide the ON/OFF the refresh adds), the handlers' end -> our code, and the one game reader of
# each byte -> `mov w8, #0`, so the bytes mean nothing else to the game.
PRR_ENTRIES = [
    (0x3CBA94,                                              # "System|GameText Errors: " -> "PRR|Offline (restart):  "
     (0x74737953, 0x477C6D65, 0x54656D61, 0x20747865, 0x6F727245, 0x203A7372, 0x73694400),
     (0x7C525250, 0x6C66664F, 0x20656E69, 0x73657228, 0x74726174, 0x20203A29, 0x73694400)),
    (0x40F2E8,                                              # "Crew|Disp Random Timer: " -> "PRR|Pin date (restart): "
     (0x65724300, 0x69447C77, 0x52207073, 0x6F646E61, 0x6954206D, 0x3A72656D, 0x75430020),
     (0x52525000, 0x6E69507C, 0x74616420, 0x72282065, 0x61747365, 0x3A297472, 0x75430020)),
    (0xA6A930, (0x140F1F7E,), (0x140F1367,)),               # entry 196 handler: b 0xe32728 -> b 0xe2f6cc (toggle_saved)
    (0xA7116C, (0xD65F03C0,), (0x1415EE56,)),               # entry 186 handler: ret -> b 0xfecac4 (pin_saved)
    (0x106CA1C, (0x39400108,), (0x52800008,)),              # GameText errors check: ldrb w8, [x8] -> mov w8, #0
    (0x14FF74C, (0x39400108,), (0x52800008,)),              # Crew random timer: ldrb w8, [x8] -> mov w8, #0
]
SETTINGS_HOOKS_V5 = [
    (0xBD3B74, (0xD65F03C0,), (0x14096DD0,)),               # AI Skill setter: ret -> b 0xe2f2b4 (settings_save)
    (0x12F1C0C, (0xD65F03C0,), (0x17ECF5C5,)),              # ret -> b 0xe2f320 (settings_load)
    (0xA685E8, (0x940F2850,), (0x940F1C39,)),               # race toggle: bl 0xe32728 -> bl 0xe2f6cc (toggle_saved)
    (0xA6885C, (0x140F27B3,), (0x140F1B9C,)),               # server time toggle: b 0xe32728 -> b 0xe2f6cc
] + PRR_ENTRIES
# GOT entries of the two PRR bytes (tools/rr3_offline.py reads the first).
OFFLINE_GOT, PIN_GOT = 0x1F6E5E0, 0x1F6E6B8
# part "settings": {version: sites}; patch writes the latest.
SETTINGS = {
    1: [(0xE2F2B4, CAVE_DEVELIFIED, CAVE_V1)] + SETTINGS_HOOKS,
    2: [(0xE2F2B4, CAVE_DEVELIFIED, CAVE_V2), (0xE2F6CC, GAP_DEVELIFIED[:11], GAP_V2),
        (0xA685E4, (0x39000109,), (0x140F1C3A,))]           # race toggle: strb w9, [x8] -> b 0xe2f6cc
       + SETTINGS_HOOKS,
    3: [(0xE2F2B4, CAVE_DEVELIFIED, CAVE_V3), (0xE2F6CC, GAP_DEVELIFIED[:11], GAP_V3),
        (0xA685E4, (0x39000109,), (0x140F1C3A,))]           # race toggle: strb w9, [x8] -> b 0xe2f6cc
       + SETTINGS_HOOKS,
    4: [(0xE2F2B4, CAVE_DEVELIFIED, CAVE_V4), (0xE2F6CC, GAP_DEVELIFIED, GAP_V4)] + SETTINGS_HOOKS_V4,
    5: [(0xE2F2B4, CAVE_V5_DEVELIFIED, CAVE_V5), (0xE2F6CC, GAP_DEVELIFIED, GAP_V5),
        (PIN_AT, PIN_DEVELIFIED, PIN_V5), (OPEN_AT, (0,) * len(OPEN_V5), OPEN_V5)] + SETTINGS_HOOKS_V5,
}
SETTINGS_LATEST = max(SETTINGS)

# Part "trim" v1: the filter (git history of tools/asm/rr3_debug_menu_filter.s)
# at 0xe2f40c, right after the settings code, with the prefixes "AI|",
# "Character|" and "Debug Race Selector". FILTER_DEVELIFIED = the
# SetupSaleCheats words it replaces.
FILTER_DEVELIFIED = (
    0xD10103A8, 0xEB00011F, 0x540000A0, 0xB40000E0, 0xF9400008, 0xF9401508,
    0x14000003, 0xF9400008, 0xF9401108, 0xD63F0100, 0x394003E8, 0x36000068,
    0xF9400BE0, 0x943FA1C4, 0x394063E8, 0xA9422BE9, 0xA9007FFF, 0xF9000BFF,
    0xD341FD0B, 0x7200011F, 0x9A890174, 0x91006288, 0x9A8A0335, 0xB100411F,
    0x540014C2, 0xF100591F, 0x540000C8, 0x531F7A88, 0x910003E9, 0x390003E8,
    0xB2400136, 0x1400000A, 0x9100A288,
)
assert CAVE_V5_DEVELIFIED[len(CAVE_DEVELIFIED):] == FILTER_DEVELIFIED[:27]
FILTER = (
    0x39400029, 0x37000069, 0x91000429, 0x14000002, 0xF9400829, 0x1000026A,
    0x3940014B, 0x3400018B, 0xAA0903EC, 0x3840154B, 0x340000EB, 0x3840158D,
    0x6B0D017F, 0x54FFFF80, 0x3840154B, 0x35FFFFEB, 0x17FFFFF6, 0xFC170FEC,
    0x17FFDCA2, 0xB944E809, 0x1100052A, 0xB904E80A, 0x2A0903E0, 0xD65F03C0,
    0x007C4941, 0x72616843, 0x65746361, 0x44007C72, 0x67756265, 0x63615220,
    0x65532065, 0x7463656C, 0x0000726F,
)
# Part "trim" v2 (issue #225): tools/asm/rr3_debug_menu_filter.s linked for
# 0x1584104, this tool's slice 0x1584104..0x1584304 of the dead physics-state
# compare (cave 0x1583704..0x15846a8, tables/lib-code-caves.csv; the rest of
# the slice is zeroed). Adds "Web Browser|PRR", "Time|", "Time Trials|WTT|"
# and eight full "Car|..." labels.
FILTER2_AT, FILTER2_END = 0x1584104, 0x1584304
FILTER2 = (
    0x39400029, 0x37000069, 0x91000429, 0x14000002, 0xF9400829, 0x1000026A,
    0x3940014B, 0x3400018B, 0xAA0903EC, 0x3840154B, 0x340000EB, 0x3840158D,
    0x6B0D017F, 0x54FFFF80, 0x3840154B, 0x35FFFFEB, 0x17FFFFF6, 0xFC170FEC,
    0x17E28964, 0xB944E809, 0x1100052A, 0xB904E80A, 0x2A0903E0, 0xD65F03C0,
    0x007C4941, 0x72616843, 0x65746361, 0x44007C72, 0x67756265, 0x63615220,
    0x65532065, 0x7463656C, 0x5700726F, 0x42206265, 0x73776F72, 0x507C7265,
    0x54005252, 0x7C656D69, 0x6D695400, 0x72542065, 0x736C6169, 0x5454577C,
    0x6143007C, 0x61447C72, 0x6567616D, 0x72614320, 0x72614300, 0x6765447C,
    0x65646172, 0x72614320, 0x72614300, 0x7065527C, 0x20726961, 0x00726143,
    0x7C726143, 0x6F6D6552, 0x55206576, 0x61726770, 0x20736564, 0x6D6F7246,
    0x6C6C4120, 0x72614320, 0x61430073, 0x65527C72, 0x65766F6D, 0x67705520,
    0x65646172, 0x72462073, 0x43206D6F, 0x43007261, 0x527C7261, 0x766F6D65,
    0x61432065, 0x61430072, 0x65527C72, 0x65766F6D, 0x6C6C4120, 0x72614320,
    0x61430073, 0x6F547C72, 0x656C6767, 0x50495620, 0x00000000,
)
# Part "trim" v3 (issue #215): same code and slice as v2, other prefixes:
# Character keeps four full labels (Unlock Everything, Unlock Next Series,
# Save game, Validate user data) instead of "Character|", and Car|Toggle VIP
# is gone. tools/asm/rr3_debug_menu_filter.s linked for 0x1584104.
FILTER3 = (
    0x39400029, 0x37000069, 0x91000429, 0x14000002, 0xF9400829, 0x1000026A,
    0x3940014B, 0x3400018B, 0xAA0903EC, 0x3840154B, 0x340000EB, 0x3840158D,
    0x6B0D017F, 0x54FFFF80, 0x3840154B, 0x35FFFFEB, 0x17FFFFF6, 0xFC170FEC,
    0x17E28964, 0xB944E809, 0x1100052A, 0xB904E80A, 0x2A0903E0, 0xD65F03C0,
    0x007C4941, 0x72616843, 0x65746361, 0x6E557C72, 0x6B636F6C, 0x65764520,
    0x68747972, 0x00676E69, 0x72616843, 0x65746361, 0x6E557C72, 0x6B636F6C,
    0x78654E20, 0x65532074, 0x73656972, 0x61684300, 0x74636172, 0x537C7265,
    0x20657661, 0x656D6167, 0x61684300, 0x74636172, 0x567C7265, 0x64696C61,
    0x20657461, 0x72657375, 0x74616420, 0x65440061, 0x20677562, 0x65636152,
    0x6C655320, 0x6F746365, 0x65570072, 0x72422062, 0x6573776F, 0x52507C72,
    0x69540052, 0x007C656D, 0x656D6954, 0x69725420, 0x7C736C61, 0x7C545457,
    0x72614300, 0x6D61447C, 0x20656761, 0x00726143, 0x7C726143, 0x72676544,
    0x20656461, 0x00726143, 0x7C726143, 0x61706552, 0x43207269, 0x43007261,
    0x527C7261, 0x766F6D65, 0x70552065, 0x64617267, 0x46207365, 0x206D6F72,
    0x206C6C41, 0x73726143, 0x72614300, 0x6D65527C, 0x2065766F, 0x72677055,
    0x73656461, 0x6F724620, 0x6143206D, 0x61430072, 0x65527C72, 0x65766F6D,
    0x72614320, 0x72614300, 0x6D65527C, 0x2065766F, 0x206C6C41, 0x73726143,
    0x00000000,
)
# Part "trim" v4 (issue #318): v3 plus a blue Character > Unlock submenu.
# Two .rodata label words: the space after "Unlock" becomes "|", so
# "Character|Unlock Everything" (0x4738f8) and "Character|Unlock Next Series"
# (0x4631a8) become "Character|Unlock|Everything" / "|Next Series" (same
# length; each string is read only by the label initializer, 0xe199a8 and
# 0xe19a14). AddCheat gives every label part but the last the
# btn_store_blue.png button. The filter keeps both with one prefix,
# "Character|Unlock|", instead of v3's two full labels.
UNLOCK_LABELS = [
    (0x473908, (0x65764520,), (0x6576457C,)),                # " Eve" -> "|Eve"
    (0x4631B8, (0x78654E20,), (0x78654E7C,)),                # " Nex" -> "|Nex"
]
FILTER4 = (
    0x39400029, 0x37000069, 0x91000429, 0x14000002, 0xF9400829, 0x1000026A,
    0x3940014B, 0x3400018B, 0xAA0903EC, 0x3840154B, 0x340000EB, 0x3840158D,
    0x6B0D017F, 0x54FFFF80, 0x3840154B, 0x35FFFFEB, 0x17FFFFF6, 0xFC170FEC,
    0x17E28964, 0xB944E809, 0x1100052A, 0xB904E80A, 0x2A0903E0, 0xD65F03C0,
    0x007C4941, 0x72616843, 0x65746361, 0x6E557C72, 0x6B636F6C, 0x6843007C,
    0x63617261, 0x7C726574, 0x65766153, 0x6D616720, 0x68430065, 0x63617261,
    0x7C726574, 0x696C6156, 0x65746164, 0x65737520, 0x61642072, 0x44006174,
    0x67756265, 0x63615220, 0x65532065, 0x7463656C, 0x5700726F, 0x42206265,
    0x73776F72, 0x507C7265, 0x54005252, 0x7C656D69, 0x6D695400, 0x72542065,
    0x736C6169, 0x5454577C, 0x6143007C, 0x61447C72, 0x6567616D, 0x72614320,
    0x72614300, 0x6765447C, 0x65646172, 0x72614320, 0x72614300, 0x7065527C,
    0x20726961, 0x00726143, 0x7C726143, 0x6F6D6552, 0x55206576, 0x61726770,
    0x20736564, 0x6D6F7246, 0x6C6C4120, 0x72614320, 0x61430073, 0x65527C72,
    0x65766F6D, 0x67705520, 0x65646172, 0x72462073, 0x43206D6F, 0x43007261,
    0x527C7261, 0x766F6D65, 0x61432065, 0x61430072, 0x65527C72, 0x65766F6D,
    0x6C6C4120, 0x72614320, 0x00000073,
)
# Part "trim" v5 (issue #215): v4 plus the prefixes "Party Play|" and "PRR|"
# at the end of the list (tools/asm/rr3_debug_menu_filter.s linked for
# 0x1584104; code words as v2-v4). 97 words, 31 free in the slice.
FILTER5 = (
    0x39400029, 0x37000069, 0x91000429, 0x14000002, 0xF9400829, 0x1000026A,
    0x3940014B, 0x3400018B, 0xAA0903EC, 0x3840154B, 0x340000EB, 0x3840158D,
    0x6B0D017F, 0x54FFFF80, 0x3840154B, 0x35FFFFEB, 0x17FFFFF6, 0xFC170FEC,
    0x17E28964, 0xB944E809, 0x1100052A, 0xB904E80A, 0x2A0903E0, 0xD65F03C0,
    0x007C4941, 0x72616843, 0x65746361, 0x6E557C72, 0x6B636F6C, 0x6843007C,
    0x63617261, 0x7C726574, 0x65766153, 0x6D616720, 0x68430065, 0x63617261,
    0x7C726574, 0x696C6156, 0x65746164, 0x65737520, 0x61642072, 0x44006174,
    0x67756265, 0x63615220, 0x65532065, 0x7463656C, 0x5700726F, 0x42206265,
    0x73776F72, 0x507C7265, 0x54005252, 0x7C656D69, 0x6D695400, 0x72542065,
    0x736C6169, 0x5454577C, 0x6143007C, 0x61447C72, 0x6567616D, 0x72614320,
    0x72614300, 0x6765447C, 0x65646172, 0x72614320, 0x72614300, 0x7065527C,
    0x20726961, 0x00726143, 0x7C726143, 0x6F6D6552, 0x55206576, 0x61726770,
    0x20736564, 0x6D6F7246, 0x6C6C4120, 0x72614320, 0x61430073, 0x65527C72,
    0x65766F6D, 0x67705520, 0x65646172, 0x72462073, 0x43206D6F, 0x43007261,
    0x527C7261, 0x766F6D65, 0x61432065, 0x61430072, 0x65527C72, 0x65766F6D,
    0x6C6C4120, 0x72614320, 0x61500073, 0x20797472, 0x79616C50, 0x5250007C,
    0x00007C52,
)
# Part "trim" v6 (issue #215, Tom 2026-11-07): v5 with the full label
# "Character|Give driver levels" (entry 22, one level per tap) added after
# Validate user data, and the Car labels Remove Upgrades From All Cars (68),
# Remove Car (72) and Remove All Cars (73) dropped. Code words as v2-v5;
# 87 words, 41 free in the slice.
FILTER6 = (
    0x39400029, 0x37000069, 0x91000429, 0x14000002, 0xF9400829, 0x1000026A,
    0x3940014B, 0x3400018B, 0xAA0903EC, 0x3840154B, 0x340000EB, 0x3840158D,
    0x6B0D017F, 0x54FFFF80, 0x3840154B, 0x35FFFFEB, 0x17FFFFF6, 0xFC170FEC,
    0x17E28964, 0xB944E809, 0x1100052A, 0xB904E80A, 0x2A0903E0, 0xD65F03C0,
    0x007C4941, 0x72616843, 0x65746361, 0x6E557C72, 0x6B636F6C, 0x6843007C,
    0x63617261, 0x7C726574, 0x65766153, 0x6D616720, 0x68430065, 0x63617261,
    0x7C726574, 0x696C6156, 0x65746164, 0x65737520, 0x61642072, 0x43006174,
    0x61726168, 0x72657463, 0x7669477C, 0x72642065, 0x72657669, 0x76656C20,
    0x00736C65, 0x75626544, 0x61522067, 0x53206563, 0x63656C65, 0x00726F74,
    0x20626557, 0x776F7242, 0x7C726573, 0x00525250, 0x656D6954, 0x6954007C,
    0x5420656D, 0x6C616972, 0x54577C73, 0x43007C54, 0x447C7261, 0x67616D61,
    0x61432065, 0x61430072, 0x65447C72, 0x64617267, 0x61432065, 0x61430072,
    0x65527C72, 0x72696170, 0x72614320, 0x72614300, 0x6D65527C, 0x2065766F,
    0x72677055, 0x73656461, 0x6F724620, 0x6143206D, 0x61500072, 0x20797472,
    0x79616C50, 0x5250007C, 0x00007C52,
)
# Part "trim" v7 (issue #590, Tom 2026-11-09): v6 plus the full labels
# "Character|Clear money & gold" (entry 27, after Give driver levels) and
# "Car|Toggle VIP" (75, after Remove Upgrades From Car), and "Time Trials|"
# instead of "Time Trials|WTT|" (the whole Time Trials menu: static 53-56
# and the TTC / WTT entries added by 0xe2ea74). Code words as v2-v6;
# 97 words, 31 free in the slice.
FILTER7 = (
    0x39400029, 0x37000069, 0x91000429, 0x14000002, 0xF9400829, 0x1000026A,
    0x3940014B, 0x3400018B, 0xAA0903EC, 0x3840154B, 0x340000EB, 0x3840158D,
    0x6B0D017F, 0x54FFFF80, 0x3840154B, 0x35FFFFEB, 0x17FFFFF6, 0xFC170FEC,
    0x17E28964, 0xB944E809, 0x1100052A, 0xB904E80A, 0x2A0903E0, 0xD65F03C0,
    0x007C4941, 0x72616843, 0x65746361, 0x6E557C72, 0x6B636F6C, 0x6843007C,
    0x63617261, 0x7C726574, 0x65766153, 0x6D616720, 0x68430065, 0x63617261,
    0x7C726574, 0x696C6156, 0x65746164, 0x65737520, 0x61642072, 0x43006174,
    0x61726168, 0x72657463, 0x7669477C, 0x72642065, 0x72657669, 0x76656C20,
    0x00736C65, 0x72616843, 0x65746361, 0x6C437C72, 0x20726165, 0x656E6F6D,
    0x20262079, 0x646C6F67, 0x62654400, 0x52206775, 0x20656361, 0x656C6553,
    0x726F7463, 0x62655700, 0x6F724220, 0x72657377, 0x5252507C, 0x6D695400,
    0x54007C65, 0x20656D69, 0x61697254, 0x007C736C, 0x7C726143, 0x616D6144,
    0x43206567, 0x43007261, 0x447C7261, 0x61726765, 0x43206564, 0x43007261,
    0x527C7261, 0x69617065, 0x61432072, 0x61430072, 0x65527C72, 0x65766F6D,
    0x67705520, 0x65646172, 0x72462073, 0x43206D6F, 0x43007261, 0x547C7261,
    0x6C67676F, 0x49562065, 0x61500050, 0x20797472, 0x79616C50, 0x5250007C,
    0x00007C52,
)
# The words of the dead function in the slice (128 words).
FILTER2_DEVELIFIED = (
    0xB941F688, 0xB941F669, 0x6B09011F, 0x54FFCB80, 0x90FF75C0, 0x9109CC00,
    0x97EC6E3F, 0x2A1F03F5, 0xB941FA88, 0xB941FA69, 0x6B09011F, 0x54FFCB00,
    0x90FF75C0, 0x9109CC00, 0x97EC6E37, 0x2A1F03F5, 0xB941FE88, 0xB941FE69,
    0x6B09011F, 0x54FFCA80, 0x90FF75C0, 0x9109CC00, 0x97EC6E2F, 0x2A1F03F5,
    0xB9420288, 0xB9420269, 0x6B09011F, 0x54FFCA00, 0x90FF75C0, 0x9109CC00,
    0x97EC6E27, 0x2A1F03F5, 0xB9420688, 0xB9420669, 0x6B09011F, 0x54FFC980,
    0x90FF75C0, 0x9109CC00, 0x97EC6E1F, 0x2A1F03F5, 0xB9420A88, 0xB9420A69,
    0x6B09011F, 0x54FFC900, 0x90FF75C0, 0x9109CC00, 0x97EC6E17, 0x2A1F03F5,
    0xB9420E88, 0xB9420E69, 0x6B09011F, 0x54FFC880, 0x90FF75C0, 0x9109CC00,
    0x97EC6E0F, 0x2A1F03F5, 0xB9421288, 0xB9421269, 0x6B09011F, 0x54FFC800,
    0x90FF75C0, 0x9109CC00, 0x97EC6E07, 0x2A1F03F5, 0xB9421688, 0xB9421669,
    0x6B09011F, 0x54FFC780, 0x90FF75C0, 0x9109CC00, 0x97EC6DFF, 0x2A1F03F5,
    0xB9421A88, 0xB9421A69, 0x6B09011F, 0x54FFC700, 0x90FF75C0, 0x9109CC00,
    0x97EC6DF7, 0x2A1F03F5, 0xB9422288, 0xB9422269, 0x6B09011F, 0x54FFC680,
    0xF0FF7560, 0x91303C00, 0x97EC6DEF, 0x2A1F03F5, 0xB9422688, 0xB9422669,
    0x6B09011F, 0x54FFC600, 0xF0FF7560, 0x91303C00, 0x97EC6DE7, 0x2A1F03F5,
    0xB9422A88, 0xB9422A69, 0x6B09011F, 0x54FFC580, 0xF0FF7560, 0x91303C00,
    0x97EC6DDF, 0x2A1F03F5, 0xB9422E88, 0xB9422E69, 0x6B09011F, 0x54FFC500,
    0xF0FF7560, 0x91303C00, 0x97EC6DD7, 0x2A1F03F5, 0x79446288, 0x79446269,
    0x6B09011F, 0x54FFC480, 0xB0FF7680, 0x91346400, 0x97EC6DCF, 0x2A1F03F5,
    0x79446688, 0x79446669, 0x6B09011F, 0x54FFC400, 0xB0FF7680, 0x91346400,
    0x97EC6DC7, 0x2A1F03F5,
)

# Calls v2 runs again: 0xe27878 (0xe2b174, the Time submenu) and 0xe278b0
# (0xe2ea74, Time Trials TTC and WTT); the filter then keeps only Time| and
# Time Trials|WTT| (v7: all of Time Trials|). Their other helper (0xe2f9f8) goes through AddCheat and
# only records a refresh function by index, as in the calls v1 keeps.
TRIM2_RUN = (0xE27878, 0xE278B0)
# part "trim": {version: sites}; patch writes the latest.
TRIM = {
    1: [(0xE266D8, (0xFC170FEC,), (0x1400234D,)),           # add-entry fn: str d12 -> b 0xe2f40c (filter)
        (0xE2F40C, FILTER_DEVELIFIED, FILTER)]
       + [(site, (bl,), (NOP,)) for site, bl in SKIPPED_CALLS],
    2: [(0xE266D8, (0xFC170FEC,), (0x141D768B,)),           # add-entry fn: str d12 -> b 0x1584104 (filter v2)
        (FILTER2_AT, FILTER2_DEVELIFIED, FILTER2 + (0,) * ((FILTER2_END - FILTER2_AT) // 4 - len(FILTER2)))]
       + [(site, (bl,), (NOP,)) for site, bl in SKIPPED_CALLS if site not in TRIM2_RUN],
    3: [(0xE266D8, (0xFC170FEC,), (0x141D768B,)),           # add-entry fn: str d12 -> b 0x1584104 (filter v3)
        (FILTER2_AT, FILTER2_DEVELIFIED, FILTER3 + (0,) * ((FILTER2_END - FILTER2_AT) // 4 - len(FILTER3)))]
       + [(site, (bl,), (NOP,)) for site, bl in SKIPPED_CALLS if site not in TRIM2_RUN],
    4: [(0xE266D8, (0xFC170FEC,), (0x141D768B,)),           # add-entry fn: str d12 -> b 0x1584104 (filter v4)
        (FILTER2_AT, FILTER2_DEVELIFIED, FILTER4 + (0,) * ((FILTER2_END - FILTER2_AT) // 4 - len(FILTER4)))]
       + UNLOCK_LABELS
       + [(site, (bl,), (NOP,)) for site, bl in SKIPPED_CALLS if site not in TRIM2_RUN],
    5: [(0xE266D8, (0xFC170FEC,), (0x141D768B,)),           # add-entry fn: str d12 -> b 0x1584104 (filter v5)
        (FILTER2_AT, FILTER2_DEVELIFIED, FILTER5 + (0,) * ((FILTER2_END - FILTER2_AT) // 4 - len(FILTER5)))]
       + UNLOCK_LABELS
       + [(site, (bl,), (NOP,)) for site, bl in SKIPPED_CALLS if site not in TRIM2_RUN],
    6: [(0xE266D8, (0xFC170FEC,), (0x141D768B,)),           # add-entry fn: str d12 -> b 0x1584104 (filter v6)
        (FILTER2_AT, FILTER2_DEVELIFIED, FILTER6 + (0,) * ((FILTER2_END - FILTER2_AT) // 4 - len(FILTER6)))]
       + UNLOCK_LABELS
       + [(site, (bl,), (NOP,)) for site, bl in SKIPPED_CALLS if site not in TRIM2_RUN],
    7: [(0xE266D8, (0xFC170FEC,), (0x141D768B,)),           # add-entry fn: str d12 -> b 0x1584104 (filter v7)
        (FILTER2_AT, FILTER2_DEVELIFIED, FILTER7 + (0,) * ((FILTER2_END - FILTER2_AT) // 4 - len(FILTER7)))]
       + UNLOCK_LABELS
       + [(site, (bl,), (NOP,)) for site, bl in SKIPPED_CALLS if site not in TRIM2_RUN],
}
TRIM_LATEST = max(TRIM)

# part "modes" (issue #40): the Debug Race Selector no longer offers Hot Laps
# (mode 11) and Online Multiplayer Tournament (mode 12), which EA removed
# (game_DoSetupGameMode only logs "... Mode No Longer Supported"; Hot Laps
# crashes on the loading screen).
# The selector's mode table: 31 ints at VA 0x1f80b20 in .data, file offset
# 0x1f7eb20 (.data VA = file offset + 0x2000; sites here are file offsets).
# Indexes 12..30 develified, and the same slots with 11 and 12 taken out and
# 16 (Sandbox, the first mode of the list, index 0) twice at the end, so an
# index of 29 or 30 gives the same mode as index 0, never a removed one.
MODES_TABLE = 0x1F7EB50
MODES_DEVELIFIED = (11, 12, 13, 14, 15, 17, 18, 22, 23, 24, 25, 26, 27, 28, 29, 20, 21, 19, 30)
MODES_PATCHED = (13, 14, 15, 17, 18, 22, 23, 24, 25, 26, 27, 28, 29, 20, 21, 19, 30, 16, 16)
MODES_COUNT = 29
# DebugRaceSelectScreen fill loop (0xd98a80..0xd98ac0): for mode 0..30 it got
# the name (0x9f5194), made the string, then wrote entry indexOf(mode)
# (0x9f53a0). Same 16 instructions reordered: indexOf first, and a mode not in
# the table (-1) goes on to the next mode before any string is made.
FILL_LOOP = 0xD98A80
FILL_DEVELIFIED = (
    0x2A1503E0, 0xA9007FFF, 0xF9000BFF, 0xB9001BF5,  # mov w0, w21 ; stp xzr, xzr, [sp] ; str xzr, [sp, #0x10] ; str w21, [sp, #0x18]
    0x97F171C1, 0xAA0003E1, 0x910003E0, 0x94210574,  # bl name ; mov x1, x0 ; mov x0, sp ; bl string
    0x2A1503E0, 0xF90013FF, 0x97F1723E, 0xF9400288,  # mov w0, w21 ; str xzr, [sp, #0x20] ; bl indexOf ; ldr x8, [x20]
    0x910003E1, 0x9B392016, 0xAA1603E0, 0x943B3ADF,  # mov x1, sp ; smaddl x22, w0, w25, x8 ; mov x0, x22 ; bl assign
)
FILL_PATCHED = (
    0x2A1503E0, 0x97F17247, 0x37FFFF60, 0xF9400288,  # mov w0, w21 ; bl 0x9f53a0 (indexOf) ; tbnz w0, #31, 0xd98a74 ; ldr x8, [x20]
    0x9B392016, 0xA9007FFF, 0xF9000BFF, 0xA901FFF5,  # smaddl x22, w0, w25, x8 ; stp xzr, xzr, [sp] ; str xzr, [sp, #0x10] ;
                                                     # stp x21, xzr, [sp, #0x18] (mode, and the old str xzr, [sp, #0x20])
    0x2A1503E0, 0x97F171BC, 0xAA0003E1, 0x910003E0,  # mov w0, w21 ; bl 0x9f5194 (name) ; mov x1, x0 ; mov x0, sp
    0x9421056F, 0x910003E1, 0xAA1603E0, 0x943B3ADF,  # bl 0x15da06c (string) ; mov x1, sp ; mov x0, x22 ; bl 0x1c67638 (assign)
)
# Saved mode index clamp: DebugRaceSelect.2.cfg holds the selected mode index
# (cfg +0xc; loader 0x9f4c08, base in x19) and nothing checks it. The loader's
# `bl fclose` goes to MODES_CAVE first: an index >= 29 (unsigned) becomes 0.
MODES_CAVE = 0x1BAC8F0                               # zero padding (tables/lib-code-caves.csv)
MODES_CAVE_CODE = (
    0xB9400E68,                                      # ldr  w8, [x19, #0xc]
    0x7100751F,                                      # cmp  w8, #29
    0x1A8823E8,                                      # csel w8, wzr, w8, hs
    0xB9000E68,                                      # str  w8, [x19, #0xc]
    0x1409ACFC,                                      # b    0x1e17cf0 (fclose@plt)
)
MODES = [
    (MODES_TABLE, MODES_DEVELIFIED, MODES_PATCHED),
    (0x9F6FF0, (0xF1007F7F,), (0xF100777F,)),        # ImGui combo: cmp x27, #0x1f -> #0x1d
    (0xD98A04, (0xF100797F,), (0xF100717F,)),        # screen rows: cmp x11, #0x1e -> #0x1c
    (0xD98A0C, (0x528003E8,), (0x528003A8,)),        # mov w8, #0x1f -> #0x1d
    (0xD98A20, (0xF113615F,), (0xF112215F,)),        # cmp x10, #0x4d8 -> #0x488 (31 / 29 entries of 40 bytes)
    (0xD98A28, (0x91136135,), (0x91122135,)),        # add x21, x9, #0x4d8 -> #0x488
    (FILL_LOOP, FILL_DEVELIFIED, FILL_PATCHED),
    (0x9F4E30, (0x94508BB0,), (0x9446DEB0,)),        # cfg loader: bl 0x1e17cf0 (fclose) -> bl 0x1bac8f0
    (MODES_CAVE, (0,) * len(MODES_CAVE_CODE), MODES_CAVE_CODE),
]

# part "menu": {version: sites}; patch writes the latest.
# v2 (issue #635): the corner-tap gate 0x10e8dfc calls menu_gate
# (tools/asm/rr3_debug_menu_gate.s, 41 words at 0xfecb10, this tool's slice
# 0xfecb10..0xfecbb4 of the dead benchmark-table function, cave
# 0xfec9c4..0xfede6c): no menu or pause tweak panel in OMP, online, LTS
# (WTT, TTC, community, Seasons) and Time Trial races (the Race Selector's
# event 18130 excepted).
MENU_OPEN = (0x10E8AB4,
             (0xB0007437, 0xF942EAF7, 0xAA0003F3, 0xF94002E8),  # adrp x23 ; ldr x23 ; mov x19, x0 ; ldr x8, [x23]
             (0xAA0003F3, 0xB0007474, 0xF9469294, 0x14000039))  # mov x19, x0 ; adrp x20, 0x1f75000 ;
                                                                 # ldr x20, [x20, #0xd20] ; b 0x10e8ba4
MENU_GATE_AT = 0xFECB10
MENU_GATE_DEVELIFIED = (
    0xF9000D09, 0x3C808100, 0xA900FE9F, 0xF900029F, 0xF9400949, 0x3DC00140,
    0x9100E10A, 0xF9001909, 0x3D800900, 0xF90002EA, 0x14000008, 0x910043E1,
    0xAA1303E0, 0x940008C6, 0x394063E8, 0x36000068, 0xF94017E0, 0x9438ABFF,
    0x910043F8, 0x91002314, 0xD0FFA2E1, 0x0F030480, 0x52800028, 0x9118B821,
    0xAA1403E0, 0xA901FFFF, 0xF90017FF, 0xA903FFFF, 0xFD001BE0, 0xB90013E8,
    0x9417B539, 0x3DC003E0, 0xB90043FF, 0x3D800FE0, 0xF94002E8, 0xF94002A9,
    0xEB09011F, 0x54000222, 0xB94013E9, 0x9100830A, 0xB9000109,
)
MENU_GATE = (
    0xB0007C09, 0xF945612A, 0xF940014A, 0xB40000AA, 0xB944CD4B, 0x51000D6B,
    0x7100157F, 0x54000409, 0xF942ED2A, 0xF940014A, 0xB400036A, 0x5281B10B,
    0x72A0002B, 0xF86B694C, 0xB40002EC, 0x52818F0B, 0x72A0002B, 0xB86B694C,
    0x7100619F, 0x54000280, 0x5282740B, 0x72A0002B, 0xF86B694D, 0xB40001CD,
    0x7100499F, 0x540000A1, 0xB94001AE, 0x5288DA4F, 0x6B0F01DF, 0x54000141,
    0xF94099AD, 0xB40000CD, 0xF94085AD, 0xB400008D, 0xB94031AE, 0x71001DDF,
    0x54000060, 0x52800028, 0xD65F03C0, 0x2A1F03E8, 0xD65F03C0,
)
MENU = {
    1: [(0x10E8DFC, (0x39558408,), (0x52800028,)),          # ldrb w8, [x0, #0x561] -> mov w8, #1
        MENU_OPEN],
    2: [(0x10E8DFC, (0x39558408,), (0x97FC0F45,)),          # ldrb w8, [x0, #0x561] -> bl 0xfecb10 (menu_gate)
        MENU_OPEN,
        (MENU_GATE_AT, MENU_GATE_DEVELIFIED, MENU_GATE)],
}
MENU_LATEST = max(MENU)

# .text VMA == file offset in this build (not .data: see MODES_TABLE)
PARTS = {
    "menu": MENU[MENU_LATEST],
    "nosales": [
        (0xE278C0, (0x94001E7D,), (NOP,)),                  # bl 0xe2f2b4 (SetupSaleCheats) -> nop
    ],
    "trim": [
        *TRIM[TRIM_LATEST],
    ],
    "settings": SETTINGS[SETTINGS_LATEST],
    "race": [
        (0xD9BFE8, (0x940D31F7,), (0x52800020,)),           # bl 0x10e87c4 -> mov w0, #1
        (0xDB6E20, (0x940CC669,), (0x52800020,)),           # bl 0x10e87c4 -> mov w0, #1
        (0xD983B0, (0x940D4105,), (0x52800020,)),           # selector screen: bl 0x10e87c4 -> mov w0, #1
    ],
    "noskillcalc": [
        (0x13386CC, (0x5280202B,), (0x5280002B,)),          # mov w11, #0x101 -> mov w11, #0x1
    ],
    "modes": MODES,
    # issue #635 / #613: the pause tweak panel's "Fix Physics Steps" toggle
    # (std::function body 0x14e935c, flag 0x1f973d8) returns at once, so the
    # flag stays 0 and physics never follows the frame rate (slow motion).
    "nophysfix": [
        (0x14E935C, (0xD0005428,), (0xD65F03C0,)),          # adrp x8, 0x1f6f000 -> ret
    ],
    # #606 A8 (Tom 2026-11-11): the pause tweak panel's "Win" button (label
    # 0x430ea4, made at 0x14dfbf4) finished the race at once. Its action is
    # the member function 0x14e889c (bound through GOT 0x1f7aa00, its only
    # reference), which now returns at once, in every race.
    "nowin": [
        (0x14E889C, (0xA9BE7BFD,), (0xD65F03C0,)),          # stp x29, x30, [sp, #-0x20]! -> ret
    ],
}
DESC = {
    "menu": "three quick taps in any screen corner open the menu",
    "nosales": "Sales category off, its code holds our new code",
    "trim": "limited menu for public builds: only the entries the filter keeps",
    "race": "Debug Race Selector button can show",
    "settings": "AI Skill and Race Selector are kept in files/doc/debug_menu_settings.dat",
    "noskillcalc": "skill recalculation after races starts off",
    "modes": "Debug Race Selector doesn't offer Hot Laps or Online Multiplayer Tournament",
    "nophysfix": "pause menu's Fix Physics Steps does nothing (no slow motion)",
    "nowin": "pause menu's Win button does nothing (no instant race finish)",
}
MENU_DESC = {
    1: DESC["menu"],
    2: DESC["menu"] + ", except in OMP, online, LTS (WTT, TTC, Seasons) and Time Trial races",
}
TRIM_DESC = {
    1: "menu shows only Debug Race Selector, AI and Character",
    2: "menu shows only Debug Race Selector, AI, Character, PRR Website, Time, WTT and eight Car entries",
    3: "menu shows only Debug Race Selector, AI, four Character entries, PRR Website, Time, WTT and seven Car entries",
    4: "menu shows only Debug Race Selector, AI, four Character entries (two in a Character > Unlock submenu), "
       "PRR Website, Time, WTT and seven Car entries",
    5: "menu shows only Debug Race Selector, AI, four Character entries (two in a Character > Unlock submenu), "
       "PRR Website, Time, WTT, seven Car entries, Party Play and our own PRR category",
    6: "menu shows only Debug Race Selector, AI, five Character entries (Give driver levels; two in a "
       "Character > Unlock submenu), PRR Website, Time, WTT, four Car entries, Party Play and our own PRR category",
    7: "menu shows only Debug Race Selector, AI, six Character entries (Give driver levels, Clear money & gold; "
       "two in a Character > Unlock submenu), PRR Website, Time, the whole Time Trials menu, five Car entries "
       "(Toggle VIP), Party Play and our own PRR category",
}
SETTINGS_DESC = {
    1: "AI Skill is kept in files/doc/debug_menu_settings.dat",
    2: DESC["settings"],
    3: DESC["settings"] + " (a saved Dead loads as None)",
    4: "AI Skill, Race Selector and Override Server Time (YES unless saved NO) are kept in "
       "files/doc/debug_menu_settings.dat (a saved Dead loads as None)",
    5: "AI Skill, Race Selector, Override Server Time and the PRR entries Offline and Pin date are kept in "
       "files/doc/debug_menu_settings.dat (a saved Dead loads as None; Offline + Pin date start the clock "
       "at the pinned time)",
}

ALIASES = {"open": "menu"}                                  # part name in the old rr3_ai_menu.py


def load(path):
    data = open(path, "rb").read()
    return bytearray(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def sites_state(d, sites):
    got = set()
    for site, develified, patch in sites:
        w = struct.unpack_from(f"<{len(develified)}I", d, site)
        got.add("develified" if w == develified else "patched" if w == patch else None)
    if None in got:
        return None
    return got.pop() if len(got) == 1 else "partly patched"


def versions_sites(versions):
    """Every site any version writes, as (site, develified, develified);
    the longest range where versions differ."""
    out = {}
    for v in versions.values():
        for site, develified, _ in v:
            if len(develified) > len(out.get(site, ((),))[0]):
                out[site] = (develified,)
    return [(site, w[0], w[0]) for site, w in out.items()]


def versioned(d, versions):
    """0 develified, N for version N, None otherwise."""
    every = versions_sites(versions)
    if sites_state(d, every) == "develified":
        return 0
    for ver, sites in versions.items():
        own = {s for s, _, _ in sites}
        rest = [x for x in every if x[0] not in own]
        if sites_state(d, sites) == "patched" and (not rest or sites_state(d, rest) == "develified"):
            return ver
    return None


def settings_sites():
    return versions_sites(SETTINGS)


def settings_version(d):
    return versioned(d, SETTINGS)


def trim_version(d):
    if settings_version(d) == 5:                       # v5 holds trim v1's slice (0xe2f40c..): no v1 there
        return versioned(d, {v: s for v, s in TRIM.items() if v != 1})
    return versioned(d, TRIM)


def menu_version(d):
    return versioned(d, MENU)


VERSIONED = {"menu": (MENU, menu_version), "settings": (SETTINGS, settings_version),
             "trim": (TRIM, trim_version)}
VERSION_DESC = {"menu": MENU_DESC, "settings": SETTINGS_DESC, "trim": TRIM_DESC}


def part_state(d, part):
    if part in VERSIONED:
        v = VERSIONED[part][1](d)
        return None if v is None else "develified" if v == 0 else "patched"
    return sites_state(d, PARTS[part])


def state(d):
    out = []
    for part in PARTS:
        s = part_state(d, part)
        if s is None:
            return None
        desc = DESC[part]
        if part in VERSIONED and s == "patched":
            ver = VERSIONED[part][1](d)
            s = f"patched v{ver}"
            desc = VERSION_DESC[part][ver]
        out.append(f"{part}: {s}" + (f" ({desc})" if s.startswith("patched") else ""))
    return ", ".join(out)


def contents(d):
    """`patches` entry for rr3_build.py: '' develified, None unrecognised."""
    s = {p: part_state(d, p) for p in PARTS}
    if any(v not in ("develified", "patched") for v in s.values()):
        return None
    on = [p for p, v in s.items() if v == "patched"]
    ver = {p: VERSIONED[p][1](d) for p in VERSIONED}
    on = [p if p not in ver or ver[p] == 1 else f"{p}@v{ver[p]}" for p in on]  # only revisions carry @vN
    return "debug-menu=" + "+".join(on) if on else ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("lib")
    p = sub.add_parser("patch")
    p.add_argument("inp")
    p.add_argument("out")
    p.add_argument("--limited", action="store_true", help="also part trim (public builds): see trim above")
    p.add_argument("--parts", help="comma list of: " + ", ".join(PARTS) + " (default: all but trim)")
    p.add_argument("--settings-version", type=int, choices=sorted(SETTINGS), default=SETTINGS_LATEST,
                   help=f"settings version to write (default: latest, {SETTINGS_LATEST}); 4: no PRR entries")
    p.add_argument("--trim-version", type=int, choices=sorted(TRIM), default=TRIM_LATEST,
                   help=f"trim version to write (default: latest, {TRIM_LATEST}); 1: AI, Character and "
                        "Debug Race Selector only, filter in SetupSaleCheats")
    p.add_argument("--menu-version", type=int, choices=sorted(MENU), default=MENU_LATEST,
                   help=f"menu version to write (default: latest, {MENU_LATEST}); 1: no block in online races")
    p.add_argument("--restore", action="store_true", help="put the develified instructions back")
    a = ap.parse_args()

    d = load(a.lib if a.cmd == "check" else a.inp)
    s = state(d)
    if s is None:
        sys.exit("unexpected bytes at a patch site: not the v14.0.1 develified build?")
    if a.cmd == "check":
        print(s)
        return
    if a.parts:
        parts = [ALIASES.get(x, x) for x in a.parts.split(",") if x]
    else:
        parts = [x for x in PARTS if x != "trim" or a.limited]
    if a.limited and "trim" not in parts:
        parts.append("trim")
    bad = [x for x in parts if x not in PARTS]
    if bad:
        sys.exit(f"unknown part(s): {', '.join(bad)}")
    after = {x: ("develified" if a.restore else "patched") if x in parts else part_state(d, x) for x in PARTS}
    trim_v = (a.trim_version if "trim" in parts else trim_version(d)) if after["trim"] != "develified" else 0
    settings_v = (a.settings_version if "settings" in parts else settings_version(d)) \
        if after["settings"] != "develified" else 0
    for x in ("trim", "settings"):
        if x == "trim" and trim_v != 1:
            continue                                         # trim v2 is in its own cave slice
        if after[x] != "develified" and after["nosales"] != "patched":
            sys.exit(f"part {x} needs nosales (its code goes in SetupSaleCheats, which nosales makes unused)")
    if trim_v == 1 and (settings_v or 0) >= 5:
        sys.exit("settings v5 and trim v1 both use 0xe2f40c..0xe2f478: use --trim-version 2 or later, "
                 "or --settings-version 4")
    for part in parts:
        sites = PARTS[part]
        if part in VERSIONED:
            versions = VERSIONED[part][0]
            clear = versions
            if part == "settings" and trim_v == 1:           # keep trim v1's filter (0xe2f40c..)
                clear = {v: s for v, s in versions.items() if v < 5}
            if part == "trim" and (settings_v or 0) >= 5:    # keep settings v5's code (0xe2f40c..0xe2f478)
                clear = {v: s for v, s in versions.items() if v != 1}
            for site, develified, _ in versions_sites(clear):        # clear any version first
                struct.pack_into(f"<{len(develified)}I", d, site, *develified)
            sites = versions[{"menu": a.menu_version, "settings": a.settings_version,
                              "trim": a.trim_version}[part]]
        for site, develified, patch in sites:
            w = develified if a.restore else patch
            struct.pack_into(f"<{len(w)}I", d, site, *w)
    if (part_state(d, "nosales") == "develified"
            and hashlib.sha256(d[SALES_FN[0]:SALES_FN[1]]).hexdigest() != SALES_FN_SHA256):
        sys.exit("nosales can't be restored while SetupSaleCheats (0xe2f2b4..0xe2f70c) holds new code "
                 "(rr3_username.py? restore that first): the menu would run it")
    out = gzip.compress(bytes(d)) if a.out.endswith(".gz") else bytes(d)
    open(a.out, "wb").write(out)
    print(f"{a.out}: {state(d)}")


if __name__ == "__main__":
    main()
