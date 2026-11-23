# SnowRunner Enhanced

Preview.15 fixes the map icon’s upper-right hover and click area in enhancement #1.
It hides an unused notification placeholder through the live UI method, while
preserving both existing button actions. The preview.12 fix for the left
navigation button is retained. Live memory testing on November 23, 2026 passed
at both previously blocked points, including an on/off comparison, and the
user confirmed the result. The installed preview.15 was then tested and
confirmed in game on November 23, 2026; both repairs are active with no
instrumentation faults reported.

Windows x64 mod for SnowRunner. Version **0.1.0-preview.15** includes mouse and
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
off by default. It skips the photosensitivity warning and publisher logos by
intercepting read buffers in memory, without changing gfx.pak. This preview
requires a recognized archive hash; unsupported archives retain their intro.
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
