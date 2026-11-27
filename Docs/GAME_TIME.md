# Freeze game time / Figer l’heure du jeu

## English

In **Settings → Enhanced → GENERAL**, enable **Freeze game time** to stop the
natural day/night cycle at the current hour. It is **Off by default**. Turn it
off to resume the cycle without catching up the time spent frozen.

This option belongs to **General Improvements** and only operates in
single-player. The choice is remembered, but has no effect in co-op. The option
remains enabled across map loads; each destination keeps the time initialized
by the game. Using **Skip Time** can select a new hour while the cycle is frozen.

## Français

Dans **Paramètres → Enhanced → GÉNÉRAL**, activez **Figer l’heure du jeu** pour
arrêter le cycle naturel jour/nuit à l’heure actuelle. L’option est
**désactivée par défaut**. Désactivez-la pour reprendre le cycle sans rattraper
le temps passé à l’arrêt.

Cette option appartient aux **Améliorations générales** et fonctionne uniquement
en solo. Le choix est mémorisé, mais reste sans effet en coopération. L’option
reste activée lors des changements de carte ; chaque destination conserve
l’heure initialisée par le jeu. La commande permettant de passer le temps peut
sélectionner une nouvelle heure pendant que le cycle est figé.

## Implementation and validation

`game-time-profile.json` resolves the native clock step and singleton through
three correlated instruction signatures. Modified or ambiguous code prevents
activation. `game_time.js` uses a native instruction callback to select the
engine’s existing zero-increment branch for the current update only. It does
not write the world hour, global time modes, day/night factors, or saves.

Session access begins unknown and fails closed. Only a verified
`GameSession.CreateSinglePlayer` body with the `GameModeSingle` constructor
enables access. Session initialization, termination, and all three multiplayer
creation paths disarm it before the next clock step. A foreign native time mode
is preserved. The callback compares the current singleton with the update’s
receiver and never dereferences an object retained from a previous map.

Preferences use schema 6; schemas 1–5 migrate with `freezeGameTime=false` while
retaining previous values. The native callback is independent of the menu and
other General Improvements. Failures are included in the existing feature status.

Automated coverage includes default Off, toggle persistence, English/French menu
controls, disabled-module access, session termination, host/client co-op entry,
world replacement, conflicting time modes, changed scripts/constructors, native
signature relocation/refusal, and shared-dispatcher installation failure.

On November 27, 2026, the player confirmed in single-player that enabling the
option freezes the clock and that it remains frozen after changing maps. The
runtime report also showed the clock component ready and active in single-player,
with 27,320 frozen updates and no fault. The map names were not recorded.
Resuming time after disabling the option and co-op exclusion have automated
coverage; this player report does not validate those behaviors in-game.

Le 27 novembre 2026, le joueur a confirmé en solo que l’activation fige l’heure
et que celle-ci reste figée après un changement de carte. Le rapport du module
confirme son fonctionnement en solo sans erreur. Les cartes utilisées n’ont pas
été précisées. La reprise du temps après désactivation et l’exclusion de la
coopération sont couvertes par les tests automatisés, sans validation en jeu
dans ce retour.

The first player test found that the clock component failed compatibility
discovery. Its getter signature spanned adjacent identical functions, and the
native scanner's non-overlapping results skipped the required getter. The guard
now covers one complete getter and its padding; the clock-factors call still
uniquely identifies it. A regression test uses the real native scanner and
resolver with neighboring getters. The corrected scanner also resolves all three
guards uniquely against the full captured executable code. The successful
player test recorded above used this corrected build.
