# Paquet natif autonome

Version : `0.1.0-preview.9`. Cette intégration reprend la logique V18 avec une
correction ciblée de la lecture du périphérique par `GameStateIngame.HandleOnDeviceChanged`
dans un hôte Windows natif qui embarque **GumJS 17.26.3 / QuickJS**. Ce n’est
pas une réécriture de tous les hooks en C++. L’utilisateur final ne lance aucun
injecteur et n’installe ni Frida, ni Python, ni .NET.

## Chemin de chargement

```text
Install.cmd → SnowRunnerEnhanced.Setup.exe (Spectre.Console)
                         ↓ copie contrôlée dans Sources/Bin
SnowRunner.exe → dinput8.dll (Ultimate ASI Loader) → DirectInput système
                      ├→ SnowRunnerEnhanced.asi → InitializeASI → thread privé
                      │                            └→ config → signatures → V18
                      ├→ SnowRunnerFFBFix.asi (installé séparément)
                      └→ SMT.asi (installé séparément)
```

Le chargeur appelle `InitializeASI` après le chargement de l’ASI. Cette fonction
épingle le module et démarre une seule fois son propre thread, puis rend la main
immédiatement pour permettre le chargement des autres plugins. `DllMain` ne
crée aucun thread et n’attend rien. Enhanced s’active uniquement dans
`SnowRunner.exe`. Son runtime reste chargé jusqu’à la fin du processus ; fermer
le jeu avant toute modification ou désinstallation.

La configuration est lue avant de créer le script du correctif. L’initialisation
de base de Gum/GLib est nécessaire pour lire le JSON ; une feature désactivée
ne crée ni script ni interceptions V18. Une configuration inconnue ou invalide
laisse le correctif inactif.

Les signatures sont compilées au build depuis le profil V18. À l’exécution,
le résolveur JS recoupe les 30 blocs et leurs références, attend l’initialisation
des catégories d’entrée puis donne les octets trouvés au contrôle exact de la
V18. La découverte seule réessaie jusqu’à 30 fois (environ une minute). Un échec
d’installation des hooks ne réessaie pas. Une faute pendant le fonctionnement
repasse en observation dans la V18 et déclenche ensuite le retrait de ses hooks.

## Indépendance

Les sources, dépendances de construction, caches, configurations et paquets
restent propres à Enhanced. Le seul composant partagé dans le dossier du jeu
est Ultimate ASI Loader (`dinput8.dll`). L’installateur réutilise les copies x64
vérifiées 10.0.2 et 8.5.0 de SMT v1.5, ou installe sa propre copie téléchargée
chez l’éditeur. Les empreintes et URL sont dans `tools/asi_loaders.py`.
Il ne modifie ni les plugins ni les réglages de FFB Fix ou SMT.

Un chargeur inconnu, ses fichiers de configuration ou un proxy chaîné provoquent
un refus sans écrasement. Le chargeur reste toujours à la désinstallation, car
d’autres mods peuvent en dépendre. Enhanced possède uniquement son ASI, sa
configuration et son reçu. Une installation preview.1 doit être retirée avec
son ancien installateur ; aucun `version.dll` n’est supprimé par le nouvel outil.

Le paquet natif contient une seule feature. Ajouter une feature native
nécessitera d’ajouter son implémentation, son entrée de configuration et son option
dans l’installateur. Les options restent indépendantes ; les sous-correctifs V18
de `wheel_mouse` restent regroupés parce qu’ils partagent l’état de focus.

## Construire sous Windows x64

Outils de construction : Python 3.12 ou plus récent, SDK .NET 10.0.401,
Windows SDK 10.0.26100.0 (`Include` et `Lib`). Le script de téléchargement obtient
les outils Microsoft C++ 14.52.37025 dans `.toolchain/msvc` et le devkit GumJS
dans `vendor/frida-gumjs`, avec vérification SHA-256. Il ne modifie aucune
installation Visual Studio et n’utilise pas celle d’un projet voisin.

Exécuter les commandes depuis la racine de ce dépôt (`release/` dans un espace
d’investigation). Un clone autonome suffit : aucun fichier du dossier parent
n’est requis.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\tools\build_release.ps1 -FetchDependencies -RunTests
```

Pour réutiliser explicitement un environnement Python existant, passer son
chemin ; aucun environnement du parent n'est détecté automatiquement :

```powershell
# Depuis la racine du dépôt, dans l’espace d’investigation existant :
.\tools\build_release.ps1 -PythonExecutable ..\.venv\Scripts\python.exe -RunTests
```

Les outils C++, caches NuGet et dépendances natives restent locaux à ce dépôt.
Les tests de capture et du lanceur Python appartiennent à l’espace d’investigation
et ne font pas partie du dépôt public. Les tests de signatures, scanner, agents
V18, démarrage natif, chargeur et installateur sont autonomes dans `tests/`.

Les téléchargements et la restauration NuGet nécessitent Internet. Le paquet
final fonctionne hors ligne. Les versions NuGet sont verrouillées dans
`src/installer/packages.lock.json`, le runtime .NET embarqué est `10.0.12`.
`WINDOWS_SDK_ROOT` permet de changer le répertoire racine du SDK Windows.

`tools/asi_loaders.py` télécharge indépendamment les deux chargeurs de test
et vérifie leurs archives et DLL. Seule la copie 10.0.2 est distribuée.

Artefacts :

- `dist/SnowRunnerEnhanced-0.1.0-preview.9.zip` : paquet utilisateur et aide.
- `dist/SnowRunnerEnhanced-0.1.0-preview.9/Install.cmd` : paquet extrait.
- `build/native/build.json` : empreintes des DLL et des sources V18 embarquées.
- `vendor/manifest.json` : empreintes et provenance des dépendances natives.
- `Licenses/sources.json` : versions sources et notices des bibliothèques.

Les agents V18 embarqués sont conservés ; le profil classe désormais
`GameStateIngame.HandleOnDeviceChanged` parmi les lecteurs de pointeur. Le jeu
ne doit pas annuler sa demande de souris lors d'une notification volant déjà
convertie en comportement souris. Les lecteurs de conduite restent inchangés.
Le ZIP est assemblé
par une liste explicite ; les fixtures, journaux, téléchargements, outils de
compilation et dossiers d’autres projets ne peuvent pas y entrer par récursion.
Les rapports créés après extraction ne sont pas repris dans une reconstruction.

## Vérification et limites

Preview.9 étend la reconstruction au contrôleur de navigation partagé. La
restriction à l’appelant `HudNavigationPanelHolder.UpdateState` est supprimée ;
les 117 instructions de `NavigationPanelController.Update` et ses trois arguments
typés sont vérifiés. Chaque instance se rafraîchit une fois par changement de
préférence, quel que soit le panneau qui la possède. Les données partagées et
les méthodes d’icônes forcées restent inchangées. En preview.8, l’utilisateur
a confirmé l’actualisation de l’autre action, mais Fermer restait sur Esc lors
de clavier vers volant, panneau ouvert. Le 22 novembre 2026, après installation
de preview.9 et relancement, l’utilisateur a confirmé le scénario demandé dans
le ravitaillement et la gestion de cargaison : Fermer et les autres touches
suivent les transitions dans les deux sens, avec stabilité au repos. Le statut
du correctif est actif, sans erreur signalée. Les autres panneaux ne sont pas
validés individuellement.

Preview.8 corrige la notification manquante lorsque la catégorie native est
déjà volant après une microvariation, mais que la préférence d’icônes reste
clavier. Le mouvement volontaire programme une fois le drapeau de notification
existant (`engine+4`), seulement si le moteur a déjà la catégorie demandée et
que le drapeau est libre. Le dispatcher natif vérifié conserve la gestion des
abonnements et remet le drapeau à zéro. La catégorie et les valeurs de conduite
ne changent pas. Aucun pointeur d’interface conservé n’est rappelé directement.
Tous les lecteurs de `HintIconsPool` relèvent désormais de la présentation,
ainsi que `NavButtonController.ReSetForDevice`. Les autres classes conservent
leur classification existante. La capture passive contient les panneaux de
ravitaillement et de cargaison ; leur essai avec preview.8 a confirmé les autres
actions, mais a révélé le cas Fermer corrigé dans preview.9 ci-dessus.

Preview.7 sépare l’activité native de la préférence des icônes : une capture
du 22 novembre montre des reprises de priorité 226 et 312 ms après le clavier,
avec des écarts de direction de seulement un ou deux crans. L’utilisateur
signale que le problème disparaît moteur éteint ; la capture ne mesure pas
directement l’état moteur et ne prouve donc pas l’origine vibratoire.
Après une action clavier, un instantané des valeurs du volant sert d’ancrage.
Un déplacement cumulé de 0,001 sur un axe normalisé, ou un changement de bouton
ou de direction du pavé, rétablit la préférence volant. L’ancrage reste fixe
afin de reconnaître un mouvement volontaire lent. Le sélecteur, les lecteurs
d’icônes et la mise à jour HUD détectent aussi ce mouvement sans nouvelle
notification de catégorie. Aucune valeur d’axe, aucun horodatage natif ni
aucune catégorie moteur n’est réécrit. Une signature supplémentaire contrôle
la disposition du tableau des commandes. Le 22 novembre, l’utilisateur a confirmé
le test après installation de preview.7 et relancement : C reste affiché
15 secondes au repos moteur allumé, puis un mouvement volontaire rétablit X.
Les compteurs montrent un événement ignoré, une activation volontaire et trois
rafraîchissements HUD, sans erreur. Les autres zones restent à tester.

Preview.6 corrige le contrôle de pile ajouté dans preview.5 : le frame VM
du détenteur HUD conserve l’index de l’instruction d’appel (751), et non celui
de l’instruction suivante (752). Preview.5 pouvait être active avec zéro
rafraîchissement. Une capture passive réelle alimente désormais le contexte
de régression. Le code corrigé accepte ce contexte dans le jeu ; la validation
après relancement est désormais confirmée avec preview.7 ci-dessus.

Preview.5 rafraîchit les invites du panneau de navigation HUD une fois par
changement de préférence de périphérique. Le cache du jeu assimile clavier et
souris ; les notifications volant converties en souris pouvaient donc laisser
l’ancienne icône de station-service. Un filtre natif reconnaît exactement
`NavigationPanelController.Update`, puis contrôle les arguments, le bytecode
et l’appelant `HudNavigationPanelHolder.UpdateState`. Il active le booléen
`isForced` de cette seule invocation. Le jeu reconstruit lui-même les boutons.
Les états partagés, les notifications de pointeur et les commandes restent
inchangés. Les mouvements souris conservent la préférence volant et ne
redéclenchent pas la reconstruction. Le filtre réutilise la signature existante
de l’entrée VM ; aucune adresse de descripteur de la capture n’est embarquée.

Le 21 novembre 2026, l’utilisateur a confirmé l’essai temporaire dans une
station-service : plusieurs transitions clavier/volant sans retour Windows,
puis mouvements souris, avec icône correcte et stable. La validation du paquet
preview.5 installé a échoué à cause du contrôle de pile décrit ci-dessus ;
les autres zones restent à tester.

Preview.4 ajoute deux signatures : la mise à jour de la caméra native et son
setter de capture souris. Une reconstruction de Fonctions dans la pile de
`TruckInputController.TurnOnFunctions` programme une seule libération. À la
prochaine mise à jour de la caméra active sur le même thread (500 ms maximum),
le setter natif rétablit la position du pointeur et désactive la capture.
Les actualisations du menu et les clics caméra suivants restent libres.
Le mode observation et l'arrêt annulent la demande en attente.

Le 21 novembre 2026, l'utilisateur a confirmé le retour automatique du curseur
à l'ouverture au volant et au clavier, ainsi que la reprise caméra par clic,
avec l'essai temporaire. La trace montre trois libérations, aucune erreur,
et aucune libération supplémentaire lors des actualisations du menu.
L'utilisateur a ensuite désinstallé puis réinstallé preview.4 et relancé le jeu :
le retour automatique du curseur au clavier et au volant est confirmé avec le
paquet natif installé, le même jour.

Les tests couvrent les 541 assertions dans le vrai moteur embarqué, dont les
transitions clavier/souris/volant et l'isolation du lecteur corrigé, le
scanner natif sur mémoire synthétique, les signatures déplacées et incohérentes,
le cycle de démarrage, les changements de configuration, l’appartenance des DLL,
les conflits et verrous Windows et le chargement ASI par import DINPUT8. Une image
PE de test contient les 30 blocs déplacés et atteint l’état actif sans aucune
injection externe. Une autre image non reconnue reste inactive.

Les tests automatisés utilisent des programmes jetables construits ici.
Le 21 novembre 2026, un essai réel après installation et lancement de preview.3
a confirmé le rétablissement du survol de Fonctions et des points de treuil
après une entrée volant. Une capture passive avant correction a identifié
`GameStateIngame.HandleOnDeviceChanged` appelant `CancelShowMouse` en contexte
volant. Le nouveau test reproduit la lecture fautive avec l'ancien profil ;
les 424 assertions passent avec la correction. Le build complet passe aussi
40 tests de compatibilité et d'installation, 82 contrôles d'interface et les
scénarios des chargeurs ASI.

Restent à valider : tous les scénarios V18 avec le paquet natif, les différents
cycles de démarrage/fermeture, une session prolongée et la coexistence complète
avec FFB Fix et SMT. Les tests chargent Enhanced et un second ASI synthétique
avec les véritables chargeurs 10.0.2 et 8.5.0 ; ils ne valident pas les hooks des
trois vrais mods ensemble. L’import DINPUT8 est vérifié avant installation ;
cela ne certifie pas toutes les boutiques.
Les signatures rendent les déplacements compatibles, sans garantie contre
une refonte des instructions, de la VM ou des scripts du jeu.

Pour le premier essai en jeu, utiliser le paquet extrait, fermer le jeu et les
lanceurs Python expérimentaux, installer Enhanced, puis lancer le jeu normalement.
Vérifier le dernier diagnostic et les gestes V18 (carte, treuil, Fonctions,
souris/volant simultanés, arrêt du moteur puis fermeture par B, démarrage volontaire).
Retirer Enhanced via son installateur avant de revenir à un lanceur de test.
