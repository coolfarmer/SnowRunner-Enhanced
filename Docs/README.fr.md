# SnowRunner Enhanced — 0.1.0-preview.30

## Enhancement #6 – Steering Wheel Improvements

La preview.30 intègre l’ancien FFB Fix dans Enhanced pour corriger les oscillations anormales lors des changements de carte. L’option **Steering Wheel Improvements** est indépendante dans l’installateur et prend effet au prochain lancement. Elle est activée lors de sa première installation ; les choix existants sont préservés lors des mises à jour.

Le constructeur est désormais retrouvé par signatures et références : un déplacement du code ou un changement d’empreinte du jeu ne suffit plus à désactiver le correctif. Un changement de structure ou une détection ambiguë laisse uniquement cette amélioration inactive. Le plugin FFB séparé n’est plus requis. Le 25 novembre 2026, le joueur confirme que la preview.30 intégrée fonctionne en jeu. Voir [les détails techniques et les limites](STEERING_WHEEL.md).


Les options grisées de CARTE et VÉHICULE correspondent à un module désactivé. Activez le module dans l’installateur pour accéder à ses options au prochain lancement du jeu.

Sur les versions preview.27 et preview.28, le joueur a vérifié en jeu que les trois options de CARTE et l’option Marche arrière automatique de VÉHICULE étaient grisées lorsque leurs modules étaient désactivés. Après réactivation des modules dans l’installateur, il a confirmé que les quatre options étaient de nouveau accessibles.

## Enhancement #5 – Vehicle

Le joueur a validé la preview.25 en jeu.

Dans **ENHANCED → VÉHICULE**, désactivez **Marche arrière automatique** pour que le frein maintenu en AUTO cesse d’engager la marche arrière. Sélectionnez R pour reculer. Le réglage est activé par défaut et sauvegardé dès sa modification.

## Enhancement #4 – General Improvements

Preview.24 ajoute le défilement par maintien de Haut ou Bas dans Fonctions. La répétition commence après 420 ms puis se poursuit toutes les 140 ms environ. Après relancement avec la preview.24 installée, le joueur a confirmé le défilement continu au clavier et avec la croix directionnelle de la manette. Le volant reste à tester séparément.

Dans **Fonctions**, appuyez sur **Bas** sur la dernière action sélectionnable pour revenir à la première. **Haut** sur la première revient à la dernière. Sur une préversion existante, choisissez **Mettre à jour Enhanced** pour activer les cinq améliorations. Elles sont aussi activées sur une nouvelle installation. Vous pouvez ensuite les régler sous **Options avancées → Personnaliser les améliorations**.

Preview.17 ajoute le menu **ENHANCED** aux paramètres du jeu. Il reste actif indépendamment des améliorations sélectionnées.

Preview.15 corrige le survol et le clic dans le coin supérieur droit de l’icône
de carte, désormais regroupé dans l’enhancement nº 3 : Map. Le repère de notification inutilisé est
masqué par le code de l’interface, en conservant les deux actions existantes
des boutons. Le correctif de preview.12 pour le bouton gauche est conservé.
L’essai en mémoire du 23 novembre 2026 passe aux deux points auparavant bloqués,
avec comparaison activé/désactivé et confirmation de l’utilisateur.
La preview.15 installée a ensuite été testée et confirmée en jeu le
23 novembre 2026 : les deux correctifs sont actifs et le diagnostic
ne signale aucune erreur d’instrumentation.

Preview.11 conserve le curseur utilisable dans le menu principal après une
entrée du volant. Cette correction de l’enhancement 1 cible uniquement le
gestionnaire de changement de périphérique du menu principal. Les correctifs
en jeu sont conservés. Les tests automatisés passent ; l’utilisateur a confirmé
le correctif du menu principal le 22 novembre 2026. Le curseur peut rester
visible pendant l’usage du volant. Les scénarios en jeu ne sont pas reconfirmés
individuellement pour cette préversion.

Les touches affichées dans les panneaux ouverts suivent maintenant le passage
du clavier au volant et inversement, y compris le bouton Fermer, sans devoir
refermer le panneau. Le service commun des icônes et la navigation utilisent
la même préférence de périphérique. Essai confirmé le 22 novembre 2026 après
installation de preview.9 et relancement, dans le ravitaillement et la gestion
de cargaison, avec maintien de la stabilité des icônes au repos.

Les petites variations d’axe au repos ne reprennent plus la priorité sur les
icônes du clavier. Un mouvement cumulé de 0,1 % de la plage d’un axe, ou un
changement de bouton, rétablit les icônes du volant. Ce seuil concerne seulement
l’affichage : les valeurs de conduite restent intactes. Essai confirmé le
22 novembre 2026 avec preview.7 installée : icône clavier stable pendant
15 secondes au repos moteur allumé, puis retour de l’icône volant au mouvement.

Les touches des invites de zone s’actualisent maintenant quand on passe du
clavier au volant, sans devoir quitter puis refocaliser le jeu. Le correctif
a été confirmé dans une station-service après installation et relancement ;
les autres zones restent à tester.

Cette préversion fait réapparaître automatiquement le curseur à l’ouverture
de Fonctions, au clavier comme au volant, après avoir utilisé la souris pour
la caméra. Un nouveau clic permet toujours de reprendre la caméra.
Elle conserve aussi le correctif de survol après une entrée du volant.

Préversion Windows x64. Le paquet fonctionne sans installation de Python,
Frida ou .NET. Le rétablissement du survol de Fonctions et des points de treuil
après une entrée volant a été confirmé en jeu le 21 novembre 2026. Les tests
automatisés complètent cet essai ciblé ; la validation complète reste à faire.
Le retour automatique du curseur de preview.4 a également été confirmé au
clavier et au volant après désinstallation, réinstallation et relancement du jeu.

## Installer

1. Fermez SnowRunner et extrayez le ZIP complet dans un dossier accessible.
2. Lancez `Install.cmd`, puis choisissez votre langue et le dossier du jeu.
   L’installateur recherche les bibliothèques Steam ; la sélection manuelle
   accepte le dossier du jeu, `Sources/Bin` ou `SnowRunner.exe`.
3. Tous les correctifs sont activés par défaut. Pour en désactiver, utilisez **Options avancées > Personnaliser les améliorations**.
4. Choisissez **Installer Enhanced** pour installer immédiatement les correctifs sélectionnés.
5. Lancez le jeu normalement. Revenez dans **Voir l’état** pour consulter
   l’activation enregistrée lors du dernier lancement.

## Correctifs

**Utilisation simultanée de la souris et du volant** (`wheel_mouse`) corrige les commandes de la carte et du treuil,
la sélection et le focus du menu Fonctions ainsi que les clignotements ciblés. Il ne filtre aucune marque ni aucun
identifiant USB. La validation physique de la V18 concerne un G923 ; les
autres volants et une session prolongée restent à tester.

Le module **Véhicule** filtre le signal du volant au repos pour que le moteur reste
arrêté à la fermeture du menu Fonctions après un arrêt moteur au volant.

Vous pouvez désactiver le correctif souris et volant dans **Personnaliser les améliorations**, jeu fermé.
Le changement s’applique au prochain lancement. Map et Skip Startup Logos disposent de leurs propres options indépendantes.

## Mises à jour du jeu

La répétition des touches utilise les références du répartiteur d’événements. Le réglage de marche arrière vérifie séparément la signature de la fonction de changement de rapport.

Le correctif recherche 31 signatures et contrôle leurs références au lancement.
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

Enhanced s’installe sous le nom `SnowRunnerEnhanced.asi`. Un seul `dinput8.dll`
(Ultimate ASI Loader) peut charger Enhanced et les autres plugins ASI, comme `SMT.asi`.
L’installateur réutilise les copies x64 vérifiées 10.0.2 ou 8.5.0 de SMT v1.5,
ou ajoute la 10.0.2 si aucun chargeur n’existe. Un chargeur inconnu, une configuration
du chargeur ou un proxy chaîné bloque l’installation pour examen manuel, sans
écrasement. Les autres mods et leurs réglages sont conservés.

Le chargeur partagé est toujours conservé à la désinstallation d’Enhanced,
même si Enhanced l’avait installé. Les deux versions sont testées avec des
programmes synthétiques ; la coexistence avec les autres mods reste à valider en jeu.

Pour remplacer preview.1, désinstallez-la d’abord avec son ancien installateur.
Celui-ci retire son `version.dll` et `SnowRunnerEnhanced.dll` après vérification
de leur appartenance. L’installateur ASI ne modifie aucun `version.dll`.

## Ligne de commande

`Install.cmd --help` liste les options. Exemple :

```bat
Install.cmd --action configure --game-directory "D:\SteamLibrary\steamapps\common\SnowRunner" --wheel-mouse false --json
```

`--plain` utilise un menu numéroté. `--preview` affiche uniquement un aperçu.
Les actions explicites `install`, `configure` et `uninstall` effectuent directement
la modification demandée. `check` vérifie les fichiers et le mécanisme de chargement ;
la compatibilité des signatures est vérifiée dans le jeu.

## Enhancement #2 — Skip Startup Logos

Dans **Options avancées → Personnaliser les améliorations**, activez **Skip Startup Logos** pour sauter l’avertissement de photosensibilité et les logos Saber, Focus et Havok au prochain lancement. L’option est activée par défaut et indépendante de l’utilisation simultanée souris/volant. Désactivez-la pour retrouver les écrans d’origine au lancement suivant.

Le plugin intercepte uniquement les lectures de l’archive reconnue et adapte les données en mémoire. `gfx.pak` n’est pas modifié. Enhanced retrouve les deux animations de chargement par leur nom et vérifie leur contenu. Les autres ressources peuvent changer de place ou de contenu. Si une animation manque ou change, le jeu conserve son introduction. `armed` signifie que l’interception attend les lectures ; `active` confirme la lecture des deux changements de la séquence. Le chargement réel du jeu reste nécessaire.

Ligne de commande : `Install.cmd --action configure --game-directory "CHEMIN_DU_JEU" --skip-startup-logos true --json`. Une option omise lors de la configuration conserve sa valeur actuelle.

## Enhancement #3 : Map

- Correction du survol et du clic de l’icône de carte, à côté de Tâches et Contrats (zones gauche et supérieure droite).

Depuis preview.16, **Map** (`map`) est une option indépendante, activée par défaut, dans **Options avancées → Personnaliser les améliorations**. Elle regroupe les deux correctifs auparavant inclus dans l’enhancement nº 1. Les changements prennent effet au prochain lancement.

## Menu ENHANCED

Le menu suit la langue du jeu. En français, il affiche **ENHANCED → CARTE**. En anglais et dans toute autre langue, il affiche **ENHANCED → MAP**.

L’onglet **ENHANCED** suit **VOLANT** dans les paramètres du jeu. Il appartient au plugin lui-même et reste disponible même si toutes les améliorations facultatives sont désactivées. Il ne constitue pas une quatrième amélioration à cocher dans l’installateur.

La ligne **Pourquoi cet onglet ?** affiche une explication dans le panneau de description, sans valeur à droite. Avec l’enhancement nº 3 **Map** activé, **Sensibilité du zoom** règle immédiatement le zoom de la carte. Le nombre apparaît à droite : **0 = ×0,25, 50 = réglage d’origine du jeu, 100 = ×4**. La restauration des valeurs par défaut remet le curseur à 50. La préférence est sauvegardée dans `SnowRunnerEnhanced.settings.json`, à côté du plugin, et conservée lors des mises à jour et réinstallations.

**Sensibilité de rotation**, sous le zoom dans **ENHANCED → CARTE**, règle la rotation au clic droit maintenu : **0 = cinquante fois plus lent (×0,02), 50 = vitesse d’origine, 100 = quatre fois plus rapide**. La valeur par défaut et la restauration des valeurs par défaut sont **50**. Les changements sont immédiats ; le zoom et la rotation sont sauvegardés séparément dans le même fichier de préférences. Une ancienne préférence de zoom est conservée, avec la rotation initialisée à 50.

**Garder le nord en haut** oriente la carte vers le nord et verrouille sa rotation. Désactivez cette option pour tourner la carte librement. Elle est désactivée par défaut et votre choix est sauvegardé.
