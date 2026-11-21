# Paquet natif autonome

Version : `0.1.0-preview.1`. Cette intégration reprend la logique V18 intacte
dans un hôte Windows natif qui embarque **GumJS 17.26.3 / QuickJS**. Ce n’est
pas une réécriture de tous les hooks en C++. L’utilisateur final ne lance aucun
injecteur et n’installe ni Frida, ni Python, ni .NET.

## Chemin de chargement

```text
Install.cmd → SnowRunnerEnhanced.Setup.exe (Spectre.Console)
                         ↓ copie contrôlée dans Sources/Bin
SnowRunner.exe → version.dll → DLL VERSION du système (fonctions transmises)
                      └→ thread privé → SnowRunnerEnhanced.dll
                                             └→ config → signatures → agent V18
```

Le proxy se charge via l’import VERSION du jeu, transmet ses 17 exports à la
DLL du répertoire système et démarre un thread lors du premier appel d’un export.
Son `DllMain` ne crée pas de thread et n’attend rien. Le thread charge uniquement
la DLL Enhanced à côté du proxy, uniquement dans `SnowRunner.exe`. Il ne parcourt
aucun dossier de plugins. Le moteur et les DLL restent chargés jusqu’à la fin
du processus ; les changements et la désinstallation demandent de fermer le jeu.

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

Tous les fichiers, sources, outils, dépendances, caches et paquets sont propres
à Enhanced. L’installateur ne lit ni ne modifie les fichiers FFB Fix. Il refuse
un `version.dll` déjà présent. Il ne fait aucun chaînage avec `dinput8.dll`.

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

Artefacts :

- `dist/SnowRunnerEnhanced-0.1.0-preview.1.zip` : paquet utilisateur et aide.
- `dist/SnowRunnerEnhanced-0.1.0-preview.1/Install.cmd` : paquet extrait.
- `build/native/build.json` : empreintes des DLL et des sources V18 embarquées.
- `vendor/manifest.json` : empreintes et provenance des dépendances natives.
- `Licenses/sources.json` : versions sources et notices des bibliothèques.

Les agents V18 embarqués sont conservés sans modification de comportement. Le ZIP est assemblé
par une liste explicite ; les fixtures, journaux, téléchargements, outils de
compilation et dossiers d’autres projets ne peuvent pas y entrer par récursion.
Les rapports créés après extraction ne sont pas repris dans une reconstruction.

## Vérification et limites

Les tests couvrent les 402 assertions V18 dans le vrai moteur embarqué, le
scanner natif sur mémoire synthétique, les signatures déplacées et incohérentes,
le cycle de démarrage, les changements de configuration, l’appartenance des DLL,
les conflits et verrous Windows et le chargement par import VERSION. Une image
PE de test contient les 28 blocs déplacés et atteint l’état actif sans aucune
injection externe. Une autre image non reconnue reste inactive.

Ces tests utilisent des programmes jetables construits ici, jamais le jeu.
Restent à valider dans SnowRunner : le moment de l’appel VERSION, le démarrage
et la fermeture, les scénarios V18, une session prolongée et la coexistence réelle
avec d’autres mods. Le choix du proxy repose sur l’import VERSION observé dans
le binaire Steam de référence ; cela ne certifie pas toutes les boutiques.
Les signatures rendent les déplacements compatibles, sans garantie contre
une refonte des instructions, de la VM ou des scripts du jeu.

Pour le premier essai en jeu, utiliser le paquet extrait, fermer le jeu et les
lanceurs Python expérimentaux, installer Enhanced, puis lancer le jeu normalement.
Vérifier le dernier diagnostic et les gestes V18 (carte, treuil, Fonctions,
souris/volant simultanés, arrêt du moteur puis fermeture par B, démarrage volontaire).
Retirer Enhanced via son installateur avant de revenir à un lanceur de test.
