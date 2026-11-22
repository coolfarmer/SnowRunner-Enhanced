# SnowRunner Enhanced — 0.1.0-preview.9

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

## Fixes

**Simultaneous Mouse & Wheel Input** (`wheel_mouse`) contains all V18 corrections:
map and winch input, Function menu selection and focus, targeted flickering,
and wheel residue at rest. It does not filter by wheel brand or USB identity.
The V18 physical validation used a G923. Other wheels and extended sessions
still need physical testing.

Disable this fix through **Customize enhancements** with the game closed. Changes take
effect on the next launch. Future fixes will have independent options; this
preview contains one feature.

## Game updates

The fix searches for 31 signatures and checks their references at startup.
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
(Ultimate ASI Loader) can load Enhanced, `SnowRunnerFFBFix.asi` and `SMT.asi`.
The installer reuses the verified x64 loaders 10.0.2 or 8.5.0 from SMT v1.5,
or adds 10.0.2 when no loader exists. Unknown loaders, loader configuration
files and chained proxies require manual review and block installation without
overwriting them. Other mods and their settings are preserved.

The shared loader is always retained when Enhanced is uninstalled, even when
Enhanced originally installed it. Both loader versions are tested with synthetic
programs; running all three actual mods together still needs in-game validation.

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
