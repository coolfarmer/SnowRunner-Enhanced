# Vehicle improvements / Améliorations du véhicule

## English

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
