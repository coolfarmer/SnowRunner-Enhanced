# SnowRunner Enhanced — 0.1.0-preview.1

Windows x64 preview. No Python, Frida or .NET installation is required.
Automated validation uses disposable test programs. This native integration
still needs validation in SnowRunner.

## Install

1. Close SnowRunner and extract the complete ZIP to a writable folder.
2. Run `Install.cmd`, choose a language, then select the game folder.
   Steam libraries are detected automatically. Manual selection accepts the
   game folder, `Sources/Bin`, or `SnowRunner.exe`.
3. Use **Choose fixes** to select the corrections you want.
4. Choose **Install**, review the destination, then confirm.
5. Start the game normally. Return to **View status** to see activation from
   the last recorded game launch.

## Fixes

**Mouse and wheel coexistence** (`wheel_mouse`) contains all V18 corrections:
map and winch input, Function menu selection and focus, targeted flickering,
and wheel residue at rest. It does not filter by wheel brand or USB identity.
The V18 physical validation used a G923. Other wheels and this native loading
method still need physical testing.

Disable this fix through **Choose fixes** with the game closed. Changes take
effect on the next launch. Future fixes will have independent options; this
preview contains one feature.

## Game updates

The fix searches for 28 signatures and checks their references at startup.
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

Enhanced owns its `version.dll`, plugin DLL, configuration and installation
receipt. No SnowRunner FFB Fix files are used or modified. An existing
`version.dll` blocks installation and is preserved. The two projects use
separate files, but their simultaneous operation still needs in-game testing.

## Command line

`Install.cmd --help` lists options. For example:

```bat
Install.cmd --action configure --game-directory "D:\SteamLibrary\steamapps\common\SnowRunner" --wheel-mouse false --json
```

`--plain` uses a numbered menu. `--preview` only displays the interface.
Explicit `install`, `configure` and `uninstall` actions apply changes directly.
`check` checks files and the loading mechanism; signature compatibility is
checked in memory when the game runs.
