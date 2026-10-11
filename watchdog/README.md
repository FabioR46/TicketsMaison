# Tickets Maison — Watchdog

Petit programme qui surveille tes appareils réseau et crée un ticket quand l'un d'eux ne répond plus.
Il tourne dans **Docker Desktop**, sur un ordinateur (PC ou Mac) allumé en permanence à la maison.

## Installation (3 minutes)
1. Installe **Docker Desktop** (gratuit) : https://www.docker.com/products/docker-desktop/ — ouvre-le une fois.
2. Dans l'app Tickets Maison : **Réglages › Paramètres de la maison › Appareils › Copier le code de connexion**.
3. Double-clique sur l'installateur :
   - **Windows** : `Installer - Windows.bat`
   - **Mac** : `Installer - Mac.command`
     (la 1re fois, macOS peut le bloquer : clic droit › **Ouvrir**, ou Réglages Système › Confidentialité et sécurité › **Ouvrir quand même**)
4. Colle le code quand il est demandé, Entrée. C'est tout ✅

Le watchdog redémarre tout seul avec Docker Desktop. Vérifie juste dans Docker Desktop › Settings que
**« Start Docker Desktop when you sign in »** est coché.

## Ensuite
- Mettre à jour ou changer de maison : relance l'installateur.
- Désinstaller : `Desinstaller - Windows.bat` ou `Desinstaller - Mac.command`.
- Voir ce qu'il fait : Docker Desktop › Containers › **tickets-maison-watchdog** › Logs.
- Les appareils à surveiller se gèrent dans l'app (Paramètres de la maison › Appareils).

## Options (fichier .env, pour les curieux)
`INTERVAL` (secondes entre deux tours, 60) · `FAILS` (échecs avant ticket, 3) · `TIMEOUT` (3) · `TZ` (Europe/Paris)
