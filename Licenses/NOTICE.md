# Third-party components

This preview embeds Frida GumJS 17.26.3 in `SnowRunnerEnhanced.dll` and
.NET 10.0.12 / Spectre.Console 0.57.2 in the setup executable.
The JavaScript runtime selected by Enhanced is QuickJS. The official GumJS
static devkit also includes V8 and the libraries listed in `sources.json`.

The original notices are included alongside this file. `sources.json` identifies
the corresponding source repositories, exact dependency revisions from Frida's
release engineering manifest, notice URLs and SHA-256 digests.
SQLite is in the public domain; its source revision is also recorded there.
See <https://www.sqlite.org/copyright.html>.

Native relinking uses the generated `build/native/plugin.obj`, the official
GumJS static devkit (or a rebuilt compatible devkit), Microsoft C/C++ runtime
libraries and Windows SDK libraries. The project build script and native source
are in `tools/build_native.py` and `src/native/`; source revisions and build
instructions are in `docs/NATIVE_BUILD.md`. No library sources were taken from
SnowRunner FFB Fix, and none of its files are included in this package.
