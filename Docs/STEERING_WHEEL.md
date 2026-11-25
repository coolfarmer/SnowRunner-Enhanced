# Enhancement #6 – Steering Wheel Improvements

Introduced in `0.1.0-preview.30`. The installer label is **Steering Wheel
Improvements**, with configuration key `steering_wheel_improvements` and command
line option `--steering-wheel-improvements true|false`. New installations and
updates from configurations without this option enable it. An explicit existing
choice is preserved. Changes apply at the next game launch.

## Correction

The former SnowRunner FFB Fix is now part of `SnowRunnerEnhanced.asi`. Its native
callback initializes exactly four floats at object offsets `0x44` through `0x50`
to positive zero, at constructor entry, before the object is published. Legitimate
writes inside the constructor and later effects are preserved. It does not change
wheel gains, filter forces or call any wheel SDK. The constructor callback uses
Gum's native listener, without JavaScript, allocation, logging or a wait lock.

The callback requires all 16 bytes to lie in one committed private read/write
region, writes and reads them back, preserves LastError and permanently disarms
after a failure. Other callbacks already in flight may finish. Like the original,
this does not protect against illegal concurrent destruction of the game object.

## Relocatable compatibility

The reference is Steam `1.907887.SNOW_DLC_19`. Unlike the old standalone plugin,
Enhanced does **not** require that executable's SHA-256. The hash remains in the
diagnostic. All addresses used by the correction are discovered in readable,
executable sections before `InitializeASI` returns, independently of input-category
or settings-menu initialization. No hook is installed under `DllMain`.

The source profile contains twelve guards derived from the former thirteen:
the short producer prefix was redundant with the longer producer guard. Four
original byte ranges ended inside an instruction; the duplicate producer range
is omitted, and the three retained ranges end at the last complete instruction.
The complete constructor and transient calculation are preserved. The profile
covers the constructor, base constructor, allocations, producer, parameter getter,
transient calculation and game-side command path.

At build time the existing Capstone-based signature compiler masks only external
instruction-relative addresses. Opcodes, object offsets, constants and internal
branches remain exact. At runtime the native resolver:

1. Finds candidates for every guard in executable sections.
2. Checks reference destinations against readable/code sections.
3. Uses unique functions to disambiguate short helpers, requires shared references
   and overlapping guarded addresses to agree, and ultimately requires one
   candidate for every guard.
4. Re-reads every resolved guard before attaching to the constructor.

Functions and data can move independently. A changed object layout, changed
required instructions, missing or ambiguous signature, inconsistent reference or
failed interception leaves this enhancement inactive. Other enhancements continue.
The twelve guards are deliberately conservative: compiler changes or unrelated
edits within a guarded function may still require a profile update. Compatibility
with an unreleased game build is not claimed. No fuzzy signature fallback is used.

## Configuration and diagnosis

The installer adds the sixth option to the existing selection menu and reports
its runtime state. The status JSON includes `enabled`, `status`, `reason`,
`compatibilityMethod`, `relocatedGuards`, `armed`, `applied`, `failed` and `skipped`.
Counters refresh even if another enhancement's discovery fails.

The existing installer migration now preserves the choices for all existing
enhancements. Sources, tests and the original MIT notice are included in Enhanced;
builds do not read the sibling FFB Fix project. No separate FFB plugin is shipped
or required. The installer does not detect or remove the old standalone plugin.

## Validation

`tests/test_steering.py` runs the production C resolver and native Gum callback in
disposable hosts. It covers the reference code, independent code/data/function
relocation, changed fields and constructor instructions, inconsistent references,
ambiguity, thousands of identical getters and non-executable regions. The callback fixture checks volatile general
and SIMD registers, flags, stack arguments, return values, LastError, exact write
bounds, legitimate constructor writes, nested/reused objects, 4,000 concurrent
constructions and disarming on invalid memory. No wheel APIs are called.

The ASI loader suite additionally checks steering-only startup, coexistence with
input corrections, and isolation when steering signatures are incompatible. The
installer suite checks independent enable/disable, migration and preservation of
other settings. These tests are distinct from physical validation.

The original prototype's notes report forty map transitions without the initial
oscillations on the G923. On November 25, 2026, the player confirmed that the
integrated preview.30 works in game: “Tout fonctionne”. This is user-reported
validation of the integration; no new transition count or individual scenario
results were supplied. Compatibility with other wheels and future game builds
still requires validation.
