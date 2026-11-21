# Installer appearance

The interactive installer follows the two user-supplied terminal references.
It uses the terminal's monospace font and native window chrome; it does not
change Windows Terminal settings or share components with SnowRunner FFB Fix.

Palette: background `#262626`, text `#e6e6e6`, cyan `#00d7ff`, secondary text
`#a0a0a0`, borders `#696969`, warnings `#f5c364`. All tokens live in
`src/installer/TerminalUi.cs`.

The content is 64 columns wide with a three-column left margin. The rounded
header contains `S N O W R U N N E R` and `SnowRunner Enhanced`. A cyan `›`
marks the selected action. Disabled actions are grey and skipped by navigation.
Arrow keys wrap; Home/End select the first/last available action; Escape returns
or cancels. The main menu keeps a blank line before Exit. The language screen
uses the compact three-option arrangement in the reference.

The main menu contains installation, advanced options, more options, help, and
exit. Advanced Options contains status, feature selection, and uninstallation.
More options contains folder selection, diagnostic export, and language selection.
Automatically detected Steam installations still skip
the folder question. Feature changes retain the existing confirmation and
installation behavior.

Rendering uses a session-scoped alternate terminal screen with explicit RGB
background painting. Returning to a menu replaces the previous frame. Window
resizing reflows text, removes optional whitespace in shorter windows, and keeps
the selected action and keyboard hints visible. Long diagnostics are paginated.
Exit restores the previous screen, title, cursor, and console mode. Redirected
output and `--plain` retain numbered text menus without terminal escape codes.

Validation:

```powershell
dotnet run --project tests/installer-menu/InstallerMenuTests.csproj -c Release
.venv/Scripts/python.exe -m unittest discover -s tests -p test_release.py -v
```

The renderer checks cover 32/64/80/120 columns and 10/24/32 rows, disabled-action
navigation, full background coverage, visible selection/hints, and control
character filtering. Release tests exercise bilingual navigation and preserve
the existing install/configure/uninstall safety checks against temporary fixtures.
