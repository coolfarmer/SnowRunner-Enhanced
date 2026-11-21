# Paquet natif autonome

Version : `0.1.0-preview.3`. Cette intégration reprend la logique V18 avec une
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
le résolveur JS recoupe les 28 blocs et leurs références, attend l’initialisation
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

- `dist/SnowRunnerEnhanced-0.1.0-preview.3.zip` : paquet utilisateur et aide.
- `dist/SnowRunnerEnhanced-0.1.0-preview.3/Install.cmd` : paquet extrait.
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

Les tests couvrent les 424 assertions dans le vrai moteur embarqué, dont les
transitions clavier/souris/volant et l'isolation du lecteur corrigé, le
scanner natif sur mémoire synthétique, les signatures déplacées et incohérentes,
le cycle de démarrage, les changements de configuration, l’appartenance des DLL,
les conflits et verrous Windows et le chargement ASI par import DINPUT8. Une image
PE de test contient les 28 blocs déplacés et atteint l’état actif sans aucune
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
