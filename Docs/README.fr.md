# SnowRunner Enhanced — 0.1.0-preview.1

Préversion Windows x64. Le paquet fonctionne sans installation de Python,
Frida ou .NET. Les tests automatisés sont effectués dans des programmes de
test ; cette intégration native reste à valider dans SnowRunner.

## Installer

1. Fermez SnowRunner et extrayez le ZIP complet dans un dossier accessible.
2. Lancez `Install.cmd`, puis choisissez votre langue et le dossier du jeu.
   L’installateur recherche les bibliothèques Steam ; la sélection manuelle
   accepte le dossier du jeu, `Sources/Bin` ou `SnowRunner.exe`.
3. Dans **Choisir les correctifs**, cochez ceux que vous souhaitez utiliser.
4. Choisissez **Installer**, vérifiez la destination, puis confirmez.
5. Lancez le jeu normalement. Revenez dans **Voir l’état** pour consulter
   l’activation enregistrée lors du dernier lancement.

## Correctifs

**Cohabitation souris et volant** (`wheel_mouse`) regroupe toute la V18 :
carte et treuil, sélection et focus du menu Fonctions, clignotements ciblés
et filtrage du résidu du volant au repos. Il ne filtre aucune marque ni aucun
identifiant USB. La validation physique de la V18 concerne un G923 ; les
autres volants et le nouveau chargement natif restent à tester.

Vous pouvez désactiver ce correctif dans **Choisir les correctifs**, jeu fermé.
Le changement s’applique au prochain lancement. Les futurs correctifs auront
leurs propres options ; cette préversion ne contient qu’une feature.

## Mises à jour du jeu

Le correctif recherche 28 signatures et contrôle leurs références au lancement.
Il accepte les déplacements de code et de données compatibles sans exiger une
empreinte exacte du jeu. Si les signatures sont absentes, ambiguës ou incohérentes,
il reste inactif. La recherche peut prendre environ une minute au démarrage.
Une modification des instructions, des structures ou des scripts du jeu peut
encore nécessiter une mise à jour d’Enhanced.

**Installé** et **actif lors du dernier lancement** sont deux états différents.
Un ancien diagnostic ne garantit pas l’activation après une mise à jour du jeu.

## Diagnostic et désinstallation

**Diagnostic pour une issue GitHub** crée un fichier JSON dans `Sources/Reports`
à côté de l’installateur. Joignez-le à une issue du dépôt du projet, avec les
étapes du problème, la boutique, la version du jeu et les périphériques concernés.
Aucun rapport n’est transmis automatiquement. N’envoyez pas l’exécutable du jeu
ni une capture de sa mémoire.

Pour retirer Enhanced, fermez le jeu et choisissez **Désinstaller Enhanced**.
L’installateur vérifie l’appartenance de ses DLL avant de les enlever. Il conserve
une configuration modifiée manuellement et le dernier diagnostic ; leurs noms
sont affichés. Si une configuration conservée empêche une réinstallation,
déplacez ce fichier dans un dossier de sauvegarde après l’avoir vérifié.

Enhanced possède son propre `version.dll`, sa DLL, sa configuration et son reçu
d’installation. Aucun fichier de SnowRunner FFB Fix n’est utilisé ni modifié.
Un `version.dll` préexistant provoque un refus d’installation : il ne sera pas
écrasé. Les deux projets peuvent avoir des fichiers distincts dans le dossier du
jeu, mais leur coexistence en fonctionnement reste à valider en jeu.

## Ligne de commande

`Install.cmd --help` liste les options. Exemple :

```bat
Install.cmd --action configure --game-directory "D:\SteamLibrary\steamapps\common\SnowRunner" --wheel-mouse false --json
```

`--plain` utilise un menu numéroté. `--preview` affiche uniquement un aperçu.
Les actions explicites `install`, `configure` et `uninstall` effectuent directement
la modification demandée. `check` vérifie les fichiers et le mécanisme de chargement ;
la compatibilité des signatures est vérifiée dans le jeu.
