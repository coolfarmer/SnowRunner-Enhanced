# SnowRunner Enhanced — 0.1.0-preview.33

Preview.33 marks MAP **Active** as soon as its components are initialized and ready, without opening the map or using zoom or rotation. A failure detected during use changes the state to **Error**. MAP stays **Pending** only while initialization is incomplete.

Preview.32 fixes the invisible feature values reported in preview.31: value colors now include full opacity. States remain text on the right, without arrows. The regression test checks all 32 color bits, including alpha. In-game visual confirmation is pending.

Preview.31 adds **FEATURES** above **MAP** in the ENHANCED settings. All six installer categories show their runtime health: **Inactive** (red), **Pending** (amber), **Active** (green), or **Error** (red). These rows are read-only; select a row for contextual help. Names, states and help follow the game's English/French language.

Native diagnostics are delivered in memory every two seconds; values refresh with settings-screen updates. Some categories may wait for a relevant screen or load; MAP reports readiness without requiring first use. A component failure makes its category show Error. Active means initialized with no detected error, not a guarantee against every behavioral issue. Module selection remains in the installer, with the game closed.

Preview.31 validation: automated tests; in-game layout, colors, scrolling and continuous refresh still require confirmation.


## Enhancement #6 – Steering Wheel Improvements

Preview.30 integrates the former FFB Fix into Enhanced to correct abnormal oscillations during map transitions. **Steering Wheel Improvements** is an independent installer option, enabled when first added, with changes taking effect at the next game launch. Updates preserve existing enhancement choices.

Signatures and cross-references now locate the constructor, so moving code or changing the executable hash alone no longer disables the correction. Changed object layouts or ambiguous discovery leave only this enhancement inactive. The separate FFB plugin is no longer required. On November 25, 2026, the player confirmed that the integrated preview.30 works in game. See [implementation and limits](STEERING_WHEEL.md).


Grayed-out MAP and VEHICLE options belong to a disabled module. Enable the module in the installer to use its options the next time you start the game.

In both preview.27 and preview.28, the player verified in game that the three MAP options and the VEHICLE Automatic reverse option were grayed out when their modules were disabled and became accessible again after the modules were re-enabled.

## Enhancement #5 – Vehicle

The player confirmed the preview.25 Vehicle option works in game.

Under **ENHANCED → VEHICLE**, turn **Automatic reverse** off to keep a held brake from engaging reverse in AUTO. Select R to back up. The setting defaults to On and saves immediately.

Under **ENHANCED → VEHICLE**, **Truck Storage search** shows or hides the live search field. It defaults to On and saves immediately. Turning it off clears the search and restores the original list layout.

## Enhancement #4 – General Improvements

Preview.24 repeats Up or Down while held in Functions. Repetition starts after 420 ms and continues about every 140 ms until release. After restarting with preview.24 installed, the player confirmed continuous scrolling with both the keyboard and the controller D-pad. Steering wheel input still needs a separate test.

In **Functions**, press **Down** on the last selectable action to highlight the first, or **Up** on the first to highlight the last. For an existing preview, choose **Update Enhanced** in the installer to enable all five enhancements. You can then customize them. New installations also start with all five enabled. Find it under **Advanced Options → Customize enhancements**.

Preview.17 adds the always-on **ENHANCED** settings menu, independent of the optional enhancements.

Preview.15 fixes the map icon’s upper-right hover and click area, now grouped under enhancement #3: Map.
It hides an unused notification placeholder through the live UI method, while
preserving both existing button actions. The preview.12 fix for the left
navigation button is retained. Live memory testing on November 23, 2026 passed
at both previously blocked points, including an on/off comparison, and the
user confirmed the result. The installed preview.15 was then tested and
confirmed in game on November 23, 2026; both repairs are active with no
instrumentation faults reported.

Preview.11 keeps the cursor usable in the main menu after wheel input. This
enhancement #1 correction targets only the main menu's device-change handler.
Existing in-game fixes are preserved. Automated tests pass, and the user
confirmed the main-menu fix on November 22, 2026. The cursor can remain visible
while using the wheel. Individual in-game regression scenarios were not
separately reconfirmed for this preview.

Hints in open panels now follow keyboard-to-wheel switching and back, including
Close, without having to reopen the panel. The shared icon service and navigation
use the same device preference. Confirmed on November 22, 2026 after installing
preview.9 and restarting the game, in refuelling and cargo management, with
hints remaining stable at idle.

Small idle axis variations no longer take hint ownership away from the keyboard.
Cumulative movement of 0.1% of an axis range, or a button change, restores wheel
hints. This threshold affects presentation only; driving values remain intact.
Confirmed on November 22, 2026 with the installed preview.7: keyboard hints
stayed visible for 15 seconds at idle with the engine running, then deliberate
wheel movement restored the wheel hint.

This preview refreshes HUD zone prompts when switching between keyboard and
wheel, without having to leave and refocus the game. The gas-station test passed
after installation and restart; other zones remain to be tested.

This preview automatically restores the cursor when opening Functions with
the keyboard or wheel after using the mouse camera. Clicking again still
allows camera control. It also retains the fix for hover lost after wheel input.

Windows x64 preview. No Python, Frida or .NET installation is required.
In-game testing on November 21, 2026 confirmed restored Function menu and
winch-point hover after wheel input. Automated tests complement this targeted
check; full validation remains pending.
The preview.4 cursor fix was also confirmed with keyboard and wheel after
uninstalling, reinstalling and restarting the game.

## Install

1. Close SnowRunner and extract the complete ZIP to a writable folder.
2. Run `Install.cmd`, choose a language, then select the game folder.
   Steam libraries are detected automatically. Manual selection accepts the
   game folder, `Sources/Bin`, or `SnowRunner.exe`.
3. All fixes are enabled by default. To disable any, use **Advanced Options > Customize enhancements**.
4. Choose **Install Enhanced** to install immediately with your selected fixes.
5. Start the game normally. Return to **View status** to see activation from
   the last recorded game launch.

After installing Enhanced, check or uncheck enhancements and choose **Save**. **Updating plugin…** stays visible for at least one second and until the plugin has been uninstalled and reinstalled. Your game preferences are preserved; the choices take effect on the next launch. Saving unchanged choices does not reinstall the plugin.

**View status** lists each enhancement once, with separate **Configured** and **Last launch** columns. Recorded states use text and color: green for Active, gray for Disabled or Unknown, amber for Waiting, and red for Error. The launch timestamp uses local time. Changes since the last launch are explained below the table; narrow terminals show labeled rows instead.

## Fixes

**Simultaneous Mouse & Wheel Input** (`wheel_mouse`) corrects map and winch input,
Function menu selection and focus, and targeted flickering. It does not filter by wheel brand or USB identity.
The V18 physical validation used a G923. Other wheels and extended sessions
still need physical testing.

The **Vehicle** module filters wheel input at rest so closing the Functions menu
keeps the engine off after you stop it with the wheel.

Disable the mouse and wheel fix through **Customize enhancements** with the game closed. Changes take
effect on the next launch. Map and Skip Startup Logos have their own independent options.

## Game updates

Functions key repeat follows the resolved dispatch call and UI manager reference. Automatic reverse separately scans for the gear-shift routine and checks its field offsets and branch instructions.

The shared input scan searches for 31 signatures and checks their references at startup.
Compatible code/data relocation is accepted without requiring an exact game
hash. Missing, ambiguous or inconsistent signatures leave the fix inactive.
Startup discovery may take about a minute. Changes to instructions, data
structures or game scripts may still require an Enhanced update.

**Installed** and **active on the last recorded launch** are different states.
A previous diagnostic does not prove activation after a game update.

## Diagnostic and removal

**Diagnostic for a GitHub issue** creates a JSON file in `Sources/Reports`
beside the installer. Attach it to an issue in the project repository, together
with reproduction steps, game version, store and affected peripherals.
Nothing is uploaded automatically. Do not send the game executable or memory dumps.

Close the game and choose **Uninstall Enhanced** to remove it. DLL ownership
is verified before removal. A manually modified configuration and the last
diagnostic are retained and listed. If a retained configuration blocks a later
installation, review it and move it to a backup folder first.

Enhanced is installed as `SnowRunnerEnhanced.asi`. One shared `dinput8.dll`
(Ultimate ASI Loader) can load Enhanced and other ASI plugins, such as `SMT.asi`.
The installer reuses the verified x64 loaders 10.0.2 or 8.5.0 from SMT v1.5,
or adds 10.0.2 when no loader exists. Unknown loaders, loader configuration
files and chained proxies require manual review and block installation without
overwriting them. Other mods and their settings are preserved.

The shared loader is always retained when Enhanced is uninstalled, even when
Enhanced originally installed it. Both loader versions are tested with synthetic
programs; coexistence with other mods still needs in-game validation.

To upgrade from preview.1, first uninstall it using its original installer.
This removes the old Enhanced `version.dll` and `SnowRunnerEnhanced.dll` after
ownership checks. The ASI installer does not remove or replace any `version.dll`.

## Command line

`Install.cmd --help` lists options. For example:

```bat
Install.cmd --action configure --game-directory "D:\SteamLibrary\steamapps\common\SnowRunner" --wheel-mouse false --json
```

`--plain` uses a numbered menu. `--preview` only displays the interface.
Explicit `install`, `configure` and `uninstall` actions apply changes directly.
`check` checks files and the loading mechanism; signature compatibility is
checked in memory when the game runs.

## Enhancement #2 — Skip Startup Logos

In **Advanced Options → Customize enhancements**, enable **Skip Startup Logos** to skip the photosensitivity warning and the Saber, Focus and Havok logos on the next launch. It defaults to on and works independently of simultaneous mouse/wheel input. Disable it to restore the original sequence next launch.

The plugin changes only the read buffers of a recognized archive in memory; `gfx.pak` stays unchanged. Enhanced locates both loading movies by name in the stored graphics bundle and verifies their contents. Repacking or changing unrelated assets is supported. A changed or missing loading movie leaves the original intro in place. `armed` means the hook is waiting for reads; `active` confirms both changes for the sequence were read. Actual game loading is still required.

CLI: `Install.cmd --action configure --game-directory "GAME_PATH" --skip-startup-logos true --json`. Omitted configuration options keep their current values.

## Enhancement #3 : Map

- Fixed a bug where the Map icon (next to Tasks and Contracts) wasn't responding correctly to hovering and clicking.

Since preview.16, **Map** (`map`) is an independent option, enabled by default, in **Advanced Options → Customize enhancements**. It contains both the left and upper-right hit-area repairs previously included in enhancement #1. Changes take effect on the next launch.

## ENHANCED settings menu

The menu follows the game language. French displays **ENHANCED → CARTE**. English and all other languages display **ENHANCED → MAP**.

The **ENHANCED** tab follows **STEERING WHEEL** in the game settings. It belongs to the plugin itself and remains available with every optional enhancement disabled. It is not a fourth enhancement or an installer checkbox.

The informational row **Why am I seeing this?** displays contextual help without a value on the right. With enhancement #3 **Map** enabled, **Zoom sensitivity** controls map zoom immediately. Its numeric value appears on the right: **0 = ×0.25, 50 = the original game setting, 100 = ×4**. Restore defaults returns it to 50. The preference is saved in `SnowRunnerEnhanced.settings.json` next to the plugin and retained across upgrades and reinstalls.

**Panning sensitivity**, below zoom in **ENHANCED → MAP**, controls rotation while holding the right mouse button: **0 = fifty times slower (×0.02), 50 = original speed, 100 = four times faster**. The initial and restored default is **50**. Changes take effect immediately; zoom and rotation are saved independently in the same preferences file. Existing zoom preferences are preserved, with rotation initially set to 50.

**Keep North Up** locks the map with north at the top. Turn it off to rotate the map freely. It starts off and remembers your choice.
