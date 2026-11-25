# SnowRunner Enhanced

In both preview.27 and preview.28, the player verified in game that the three MAP options and the VEHICLE Automatic reverse option were grayed out when their modules were disabled and became accessible again after the modules were re-enabled.

## Enhancement #5 – Vehicle

The player confirmed the preview.25 Vehicle option works in game.

Under **ENHANCED → VEHICLE**, turn **Automatic reverse** off to keep a held brake from engaging reverse in AUTO. Select R to back up. The setting defaults to On and saves immediately.

## Enhancement #4 – General Improvements

Preview.24 repeats Up or Down while held in Functions. Repetition starts after 420 ms and continues about every 140 ms until release. After restarting with preview.24 installed, the player confirmed continuous scrolling with both the keyboard and the controller D-pad. Steering wheel input still needs a separate test.

Preview.23 adds wraparound navigation to **Functions**. Press Down on the last selectable action to highlight the first, or Up on the first to highlight the last. The installer enables this option by default on a new installation.

Preview.22 translates the in-game settings tab, map options and help text into English and French. Other game languages display the English text.

Preview.21 adds **Keep North Up** under **ENHANCED → MAP**. Turn it on to align a rotated map with north. Turn it off to rotate freely again. Both directions have been tested in game.

Preview.17 adds the always-on **ENHANCED** settings menu, independent of the optional enhancements.

Preview.15 fixes the map icon’s upper-right hover and click area, now grouped under enhancement #3: Map.
It hides an unused notification placeholder through the live UI method, while
preserving both existing button actions. The preview.12 fix for the left
navigation button is retained. Live memory testing on November 23, 2026 passed
at both previously blocked points, including an on/off comparison, and the
user confirmed the result. The installed preview.15 was then tested and
confirmed in game on November 23, 2026; both repairs are active with no
instrumentation faults reported.

Windows x64 mod for SnowRunner. Version **0.1.0-preview.28** includes mouse and
wheel coexistence: map and winch interaction, Function menu focus and selection,
targeted flicker fixes, and filtering of a tiny wheel input residue at rest.
Opening Functions with the keyboard or wheel now releases mouse camera capture
and restores the cursor automatically. A new click can still control the camera.
HUD zone prompts now refresh when switching between keyboard and wheel.
Open interaction panels also refresh their action hints, including Close,
without having to close and reopen the panel. The installed preview.9 passed
the keyboard/wheel switching test on November 22, 2026 after restarting the game.
Idle wheel axis chatter no longer immediately restores wheel hints after a
keyboard action. Presentation uses a 0.1% cumulative movement threshold from
the last keyboard action; buttons remain immediate and driving input is unchanged.
The installed preview.7 passed the gas-station test on November 22, 2026:
keyboard hints stayed visible for 15 seconds at idle with the engine running,
then wheel movement restored the wheel hint.

Enhancement #2, **Skip Startup Logos**, is an independent installer option,
on by default. It skips the photosensitivity warning and publisher logos by
intercepting read buffers in memory, without changing gfx.pak. This preview
locates both loading movies by name and verifies each movie before use.
The installed startup behavior was confirmed by the user on November 22, 2026.
See [implementation and validation limits](Docs/STARTUP_LOGOS.md).

The standalone package includes a bilingual installer. Players do not need to
install Python, Frida, or .NET. Extract the complete release ZIP and run
`Install.cmd`. Enhanced is an ASI plugin: a single Ultimate ASI Loader
(`dinput8.dll`) can load it alongside FFB Fix and SMT. A recognized existing
loader is reused and always retained on uninstall. The source checkout must
be built before it can be installed.

- [English installation and removal guide](Docs/README.en.md)
- [Guide français](Docs/README.fr.md)
- [Build instructions and validation limits](Docs/NATIVE_BUILD.md)
- [Installer interface](Docs/INSTALLER_UI.md)
- [Third-party notices](Licenses/)

This native integration is a preview. In-game testing on November 21, 2026
confirmed restored Function menu and winch-point hover after wheel input with
preview.3. Automated tests also cover the hooks, installer and ASI loading.
The preview.4 cursor change was confirmed with both keyboard and wheel after
uninstalling, reinstalling the package and restarting the game. The earlier
temporary test also confirmed clicking to resume camera control.
The gas-station prompt fix is confirmed after installing preview.7 and restarting
the game; other interaction zones remain to be tested.
The preview.9 panel test covered refuelling and cargo management, including
switching back to the keyboard and keeping hints stable at idle.
The earlier V18 prototype was tested with a Logitech G923. Other wheels, a full
V18 regression pass, extended sessions and coexistence with all supported mods
remain to be validated.

## Build and test

From this repository root, with Python 3.12+, .NET SDK 10.0.401, and Windows SDK
10.0.26100.0 installed:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\tools\build_release.ps1 -FetchDependencies -RunTests
```

The script downloads verified C++ tools and GumJS dependencies into ignored local
directories. Later builds can omit `-FetchDependencies`. Outputs are created in
`build/` and `dist/`; the ZIP and its `.sha256` file are release download assets.
See the build guide for using an existing Python environment.

## Repository scope

This is the single home for production sources, the installer, build and
packaging tools, synthetic regression tests, dependency metadata, and user
documentation. The native DLL embeds the JavaScript agents in `src/` using
GumJS/QuickJS; these files are required production sources.

Capture and analysis tools, experiments, raw captures, and investigation notes
are maintained outside this repository. No parent workspace files are needed
to build or test a standalone checkout. Local dependencies, generated binaries,
packages, and logs are ignored by Git.

## Enhancement #3 : Map

- Fixed a bug where the Map icon (next to Tasks and Contracts) wasn't responding correctly to hovering and clicking.

Since preview.16, **Map** (`map`) is an independent option, enabled by default, in **Advanced Options → Customize enhancements**. It contains both the left and upper-right hit-area repairs previously included in enhancement #1. Changes take effect on the next launch.

## ENHANCED settings menu

The menu follows the game language. French displays **ENHANCED → CARTE**. English and all other languages display **ENHANCED → MAP**.

The **ENHANCED** tab follows **STEERING WHEEL** in the game settings. It belongs to the plugin itself and remains available with every optional enhancement disabled. It is not a fourth enhancement or an installer checkbox.

The informational row **Why am I seeing this?** displays contextual help without a value on the right. With enhancement #3 **Map** enabled, **Zoom sensitivity** controls map zoom immediately. Its numeric value appears on the right: **0 = ×0.25, 50 = the original game setting, 100 = ×4**. Restore defaults returns it to 50. The preference is saved in `SnowRunnerEnhanced.settings.json` next to the plugin and retained across upgrades and reinstalls.

**Panning sensitivity**, below zoom in **ENHANCED → MAP**, controls rotation while holding the right mouse button: **0 = fifty times slower (×0.02), 50 = original speed, 100 = four times faster**. The initial and restored default is **50**. Changes take effect immediately; zoom and rotation are saved independently in the same preferences file. Existing zoom preferences are preserved, with rotation initially set to 50.

**Keep North Up** locks the map with north at the top. Turn it off to rotate the map freely. It starts off and remembers your choice.
