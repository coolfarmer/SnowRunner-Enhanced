# Agent instructions

These instructions apply to this repository and its subdirectories.

## Project

SnowRunner Enhanced is a Windows x64 mod for SnowRunner.
Keep the player experience simple and the improvements independently configurable.

- `src/`: production code, including the native plugin, JavaScript agents
  and C# installer.
- `tests/`: automated tests.
- `tools/`: build, verification and packaging tools.
- `Docs/`: user guides and technical documentation.
- `Licenses/`: third-party licenses and notices.
- `build/` and `dist/`: generated outputs.

This repository must remain buildable independently of its parent workspace.
Do not introduce dependencies on neighboring projects or research prototypes.

## Language

- English is the default display language and the fallback for unsupported languages.
- French must also be available for all user-facing features.
- Installer exception: preserve Windows language detection for the initial
  language selection. French may be preselected on French Windows; otherwise
  use English. Keep both languages selectable and respect the user's choice.
- Respect an explicit French selection, including the game's language
  setting for in-game interfaces.
- Add or update English and French text together: menus, descriptions,
  help text, status messages and errors.
- Keep `README.md` in English and `README_FR.md` in French, with links
  between them. English remains the default GitHub README.
- These product language rules do not dictate the language used
  to converse with the user.

## GitHub README protection

- Do not modify any README published or intended to be displayed on GitHub
  without the project owner's explicit authorization for the proposed changes.
- This includes the main README, translated READMEs and README files
  in subdirectories, even when editing them locally before publication.
- This restriction covers content, formatting, links, badges, version numbers,
  renames and deletion.
- A request to implement a feature, fix a bug, build a release or update
  documentation does not by itself authorize README changes.
- When authorization is absent, present the exact proposed text or diff
  in the conversation and wait for approval before editing the files.
- A request for a proposal authorizes drafting only.
- Once the owner approves specific changes, apply them within that scope
  without asking for the same approval again.

## Development

- Keep changes focused on the requested behavior.
- Preserve existing user preferences during updates.
- Keep optional improvements independent and preserve the ability
  to disable them.
- Preserve runtime compatibility checks. Missing or ambiguous signatures
  must leave the affected improvement inactive.
- Never claim that a game build, wheel or mod combination is supported
  solely because automated tests pass.
- Preserve unrelated mods, their configuration and shared loaders.
- Close SnowRunner before installing, replacing or removing plugin files.
- Preserve third-party attribution when reusing or modifying their code.

## Validation

- Run the tests relevant to the changed behavior.
- For a complete build and test run, use the repository's build script:

  `.\tools\build_release.ps1 -RunTests`

- Follow `Docs/NATIVE_BUILD.md` for prerequisites and dependency setup.
- Distinguish automated checks from actual in-game validation.
- Report what was tested and what still requires player confirmation.
- Do not commit generated packages, local dependencies, logs, game binaries
  or memory captures.

## Documentation style

- Write for players first: clear benefits, short steps and familiar language.
- Keep development history, implementation details and validation records
  in dedicated documentation rather than the public README.
- Describe implemented behavior accurately; do not present planned
  features as available.
