#!/bin/bash
# Tickets Maison — désinstallation du watchdog (Mac)
cd "$(dirname "$0")" || exit 1
export PATH="/usr/local/bin:/opt/homebrew/bin:$HOME/.docker/bin:$PATH"
echo "Arrêt et suppression du watchdog Tickets Maison…"
docker compose down --rmi local 2>/dev/null || docker rm -f tickets-maison-watchdog
echo "✅ Terminé. Tu peux supprimer ce dossier."
read -r -p "Appuie sur Entrée pour fermer…" _
