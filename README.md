# SnowRunner Enhanced

Windows x64 mod for SnowRunner. Version **0.1.0-preview.1** includes mouse and
wheel coexistence: map and winch interaction, Function menu focus and selection,
targeted flicker fixes, and filtering of a tiny wheel input residue at rest.

The standalone package includes a bilingual installer. Players do not need to
install Python, Frida, or .NET. Extract the complete release ZIP and run
`Install.cmd`; the source checkout must be built before it can be installed.

- [English installation and removal guide](Docs/README.en.md)
- [Guide français](Docs/README.fr.md)
- [Build instructions and validation limits](Docs/NATIVE_BUILD.md)
- [Installer interface](Docs/INSTALLER_UI.md)
- [Third-party notices](Licenses/)

This native integration is a preview validated with disposable test programs.
In-game validation of the native loading method and coexistence with other mods
is still pending. The earlier V18 prototype was tested with a Logitech G923;
other wheels remain to be validated.

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
