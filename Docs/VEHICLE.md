# Vehicle improvements / Améliorations du véhicule

## English

**Truck Storage search** adds a live search field above the stored truck list,
including modded trucks. It defaults to On. Use **Settings → ENHANCED → VEHICLE**
to hide it; Off clears the search and restores the original list layout. The
preference saves immediately and applies when returning to Truck Storage.

With **Vehicle** enabled in the installer, winching from a long trailer can find
and connect to nearby vehicle attachment points that the original truck-centered
search omitted. Cable range remains unchanged. No additional setting is needed.
The existing **Automatic reverse** preference remains independent of this fix.
Disable Vehicle in the installer and restart the game to disable its corrections.

The player confirmed the temporary memory trial on November 25, 2026: missing
points appeared, the cable connected, and pulling worked. The player also
confirmed the installed preview.34 works in game. The confirmed scenario uses mouse
selection; controller quick winch and multiplayer have not been validated.

## Français

**Recherche dans le stockage de camions** ajoute un champ de recherche instantanée
au-dessus de la liste, y compris pour les camions moddés. L’option est activée par
défaut. Dans **Paramètres → ENHANCED → VÉHICULE**, désactivez-la pour masquer le
champ, effacer la recherche et rétablir la disposition d’origine. Le choix est
sauvegardé immédiatement et appliqué au retour dans le stockage.

Lorsque **Vehicle** est activé dans l’installateur, le treuil utilisé depuis une
longue remorque peut trouver et accrocher les points de véhicules proches que
la recherche d’origine autour du camion omettait. La portée du câble reste
inchangée. Aucun réglage supplémentaire n’est nécessaire. Le réglage existant
**Marche arrière automatique** reste indépendant de cette correction.
Pour désactiver les corrections de Vehicle, désactivez cette amélioration dans
l’installateur et redémarrez le jeu.

Le joueur a confirmé l’essai temporaire en mémoire le 25 novembre 2026 : les
points manquants apparaissent, le câble s’accroche et la traction fonctionne.
Le joueur a aussi confirmé le fonctionnement du paquet preview.34 installé. Le scénario validé
utilise la sélection à la souris; le treuil rapide à la manette et le multijoueur
n’ont pas été validés.

## Implementation and validation

### Truck Storage search (preview.35)

`truck_search.js` owns the warehouse control and filtered view. The source
`truckDataList` is never edited. Search and the existing category filter are
combined, preserving the game's separate Mods only filter. Closing the warehouse
clears the query. The setting is independent of reverse and winch initialization.

The native CLIK input keeps its own caret, selection and background click
handlers. Warehouse input dispatch, device transitions and list hover yield
while that input owns focus. The first hover also calls `ActivateTruckList`
through `OnItemMouseOver`; this separate activation path is guarded as well.
Native CLIK focus events update the guard state. Other menus and explicit truck
clicks retain native behavior. Native vertical text alignment and a focus-only yellow border retain
the player-approved prototype layout. Previous row image reservations are
released before repopulating the filtered list.

`truck-search-profile.json` uses native signatures and cross-references;
warehouse methods are additionally checked against their original SSL bytecode.
Unsupported metadata stops this component and is included in Vehicle diagnostics.
Native return values are released after game-thread callbacks. Program buffers
are reused rather than allocated for each keystroke.

Preferences schema 5 adds `truckStorageSearch`. Schemas 1–4 migrate with search
enabled and preserve every existing preference. Tests cover migration, malformed
booleans, failed atomic replacement, bilingual menu accessibility, independent
setting callbacks, matching and native signature rejection.

On November 26, 2026, the complete `build_release.ps1 -RunTests` run passed:
213 installer checks, 140 Python tests, native compatibility checks, 607 native
regression checks, and all loader scenarios. These automated checks use synthetic
processes and do not establish compatibility with every game build or mod.

Live keyboard/mouse validation on the installed Steam game on November 26, 2026
confirmed that the first list hover after a full restart preserves typing focus:
Backspace continues editing without another click. The same check passed after
closing and reopening storage and after an Off/On cycle. Ctrl+A, the E key without
category changes, clicks near the input edges, end-of-text caret on refocus,
standard truck selection/preview, thumbnails, category/search combinations and
restoration of the full list after clearing the query were also checked.
Searching found the modded Aramatsu Forester entry in this save; filtering and
thumbnail rendering were checked for that entry, without deploying it. Off hides the field and
restores the native layout; On restores an empty working field without restarting.
The saved Off preference was also verified across an earlier full game restart.
Controller interaction, multiplayer and other game/mod combinations remain
unvalidated.

### Long-trailer winch fix (preview.34)

`vehicle_winch.js` supplies a borrowed vector of registered vehicles to the
selected-source discovery call and the corresponding click-time vehicle-ID
lookup. Native distance, socket eligibility, and cable creation checks remain
unchanged. It does not use vehicle origins as a range filter, which would exclude
long target trailers whose sockets are nearby. Other callers and discovery
without a selected source keep their original arguments.

`winch-profile.json` guards both functions, their callers, the socket-distance
calculation, and vehicle registry enumeration. Runtime signatures and cross
references relocate code and data without a game executable hash lock. Missing,
ambiguous, or modified signatures leave this correction inactive. Automatic
reverse has separate discovery and remains independent.

The borrowed vector is bounded to 512 registered vehicles, with four independent
buffers for overlapping calls. An invalid or larger registry, exhausted buffers,
or a memory-access error stops the winch correction and reports Vehicle as Error.
Both hooks are rolled back if initialization fails. No game-owned vector or
winch parameter is modified. This implementation preserves the validated full
candidate search rather than introducing an untested geometric approximation.

The embedded-runtime regression exercises long source and target trailers,
unchanged range rejection, native cable refusal, unrelated callers, restoration,
malformed registries, overlapping calls, guard failures, and partial installation
rollback. Signature tests cover independent code/data relocation and rejection
of missing, changed, or ambiguous code. The memory trial found 3 target sockets
instead of 0 and accepted two attachments at about 10.72 m with a 14 m range.
