# Tickets Maison pour Home Assistant

Affiche dans Home Assistant les tickets de l'app **Tickets Maison** : envoyés, en cours, en attente,
urgences, appareils surveillés hors ligne, et la liste des tickets ouverts.

## Installation avec HACS
1. HACS › menu **⋮** › **Dépôts personnalisés**
2. Colle l'adresse de ce dépôt, catégorie **Intégration**, puis **Ajouter**
3. Cherche « Tickets Maison » dans HACS › **Télécharger**
4. Redémarre Home Assistant

## Connexion
1. Dans l'app Tickets Maison : **Réglages › Home Assistant › Copier le code de connexion**
2. Home Assistant : **Paramètres › Appareils et services › Ajouter une intégration › Tickets Maison**
3. Colle le code, valide.

> Une seule fois par projet Supabase : exécuter `supabase_v5.sql` dans le SQL Editor.

## Remonter tes appareils Home Assistant dans l'app
1. Une seule fois : exécuter `supabase_v6.sql` dans Supabase (SQL Editor).
2. Paramètres › Appareils et services › Tickets Maison › **Configurer**.
3. Choisis les entités (capteurs de connectivité Ping, suivis d'appareils, prises, portes…) et,
   si tu veux, « Créer un ticket quand un appareil est hors ligne plus de 3 minutes ».
4. Elles apparaissent dans l'écran **Status** de l'app. Hors ligne = entité indisponible,
   capteur de connectivité à « off », suivi d'appareil « absent » ou capteur « problème » actif.

## Piles faibles
Dans **Configurer**, coche « Créer un ticket quand une pile ou batterie est faible » et choisis le seuil
(20 % par défaut). Toutes les batteries de Home Assistant sont surveillées, sans rien sélectionner :
un ticket « Pile faible : Détecteur cuisine » est créé sous le seuil, puis un message « ✅ Pile changée »
quand la batterie remonte.

**Référence de la pile** : installe aussi l'intégration **Battery Notes** (HACS). Elle connaît le type de pile
de milliers d'appareils (CR2032, 2× AAA…) : le ticket indique alors « 🔋 Pile à prévoir : CR2032 ».

## Entités
| Entité | Contenu |
|---|---|
| `todo.tickets_maison_a_faire` | liste « À faire » (Listes de tâches) : cocher = ticket résolu, ajouter = nouveau ticket Maintenance |
| `sensor.tickets_maison_ouverts` | tickets ouverts (attribut `tickets` = la liste) |
| `sensor.tickets_maison_envoyes` / `en_cours` / `en_attente` | compteurs par statut |
| `sensor.tickets_maison_urgents` / `a_valider` | urgences |
| `sensor.tickets_maison_resolus_jour` | résolus aujourd'hui |
| `sensor.tickets_maison_hors_ligne` | appareils hors ligne (attributs `surveilles`, `noms`) |
| `sensor.tickets_maison_dernier` | dernier ticket |
| `binary_sensor.tickets_maison_urgence` / `panne_reseau` | « Problème » si urgence / panne |

Événement `tickets_maison_nouveau_ticket` à chaque nouveau ticket (voir `automatisation_exemple.yaml`).

## Carte du tableau de bord
`carte_dashboard.yaml` : Modifier le tableau de bord › Ajouter une carte › Manuel › colle le contenu.

## Watchdog (surveillance des appareils réseau)
Le dossier `watchdog` contient un installateur en double-clic pour PC et Mac (Docker Desktop requis) :
`Installer - Windows.bat` / `Installer - Mac.command`. Voir `watchdog/README.md`.
