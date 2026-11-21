---
name: Signaler un problème
about: Incompatibilité après une mise à jour ou comportement incorrect d'un correctif
title: "[Bug] "
labels: ""
assignees: ""
---

**Problème observé**
Décrivez le symptôme, le comportement attendu et les étapes pour le reproduire.

**Versions et configuration**

- Version de SnowRunner et boutique (Steam, Epic, etc.) :
- Version de SnowRunner Enhanced :
- Features activées :
- Version de Windows :
- Volant, pédales et profil du jeu, si le problème les concerne :
- Autres mods ou correctifs chargés :

**Comparaison**

- Le problème apparaît-il avec la feature concernée désactivée ?
- Est-il apparu après une mise à jour du jeu ?

**Diagnostic**
Dans `Install.cmd`, choisissez **Diagnostic pour une issue GitHub**. Joignez le
fichier créé dans `Sources/Reports`. Il contient l'installation, les options et
le dernier état enregistré par le jeu ; indiquez si vous avez relancé le jeu
après le problème. Le statut « installé » ne prouve pas que le correctif était actif.

Ce rapport est conçu pour être partagé : empreinte du jeu, options, état et
compteurs techniques ; aucun chemin absolu, sauvegarde ou numéro de série.
N'envoyez pas l'exécutable du jeu, les captures mémoire, les archives de scripts
ou l'ensemble du dossier `logs/`.
