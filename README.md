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

## Entités
| Entité | Contenu |
|---|---|
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
