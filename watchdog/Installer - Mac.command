#!/bin/bash
# Tickets Maison — installation du watchdog (Mac)
# Double-clic pour lancer. Relancer ce fichier = mise à jour / changement de code.

cd "$(dirname "$0")" || exit 1
export PATH="/usr/local/bin:/opt/homebrew/bin:$HOME/.docker/bin:/Applications/Docker.app/Contents/Resources/bin:$PATH"
CONTAINER="tickets-maison-watchdog"

clear
echo "==============================================="
echo "   Tickets Maison — Installation du watchdog"
echo "==============================================="
echo

finish() { echo; read -r -p "Appuie sur Entrée pour fermer…" _; exit "${1:-0}"; }

# 1. Docker installé ?
if ! command -v docker >/dev/null 2>&1; then
  echo "❌ Docker Desktop n'est pas installé."
  echo "   La page de téléchargement va s'ouvrir : installe-le, ouvre-le une fois,"
  echo "   puis relance ce fichier."
  open "https://www.docker.com/products/docker-desktop/"
  finish 1
fi

# 2. Docker démarré ?
if ! docker info >/dev/null 2>&1; then
  echo "⏳ Démarrage de Docker Desktop…"
  open -a Docker 2>/dev/null
  for _ in $(seq 1 60); do
    sleep 3
    docker info >/dev/null 2>&1 && break
  done
  if ! docker info >/dev/null 2>&1; then
    echo "❌ Docker ne répond pas. Ouvre Docker Desktop, attends la baleine verte, puis relance ce fichier."
    finish 1
  fi
fi
echo "✅ Docker est prêt."
echo

# 3. Code de connexion
CODE=""
if [ -f .env ] && grep -q '^TM_CODE=TM1:' .env; then
  read -r -p "Une configuration existe déjà. La garder ? (O/n) " KEEP
  case "$KEEP" in [nN]*) ;; *) CODE=$(grep '^TM_CODE=' .env | head -1 | cut -d= -f2-) ;; esac
fi
while [ -z "$CODE" ]; do
  echo "Dans l'app Tickets Maison :"
  echo "  Réglages › Paramètres de la maison › Appareils › « Copier le code de connexion »"
  echo
  read -r -p "Colle le code ici puis Entrée : " CODE
  CODE=$(echo "$CODE" | tr -d '[:space:]"'"'")
  case "$CODE" in
    TM1:*) ;;
    *) echo "⚠️  Ce n'est pas un code valide (il commence par TM1:). Réessaie."; echo; CODE="" ;;
  esac
done

cat > .env <<ENV
TM_CODE=$CODE
INTERVAL=60
FAILS=3
TIMEOUT=3
TZ=Europe/Paris
ENV

# 4. Construction + démarrage (redémarre tout seul avec Docker)
echo
echo "⏳ Installation (la première fois : 1 à 2 minutes)…"
if ! docker compose up -d --build; then
  echo "❌ L'installation a échoué (voir les messages ci-dessus)."
  finish 1
fi

echo
echo "⏳ Vérification…"
sleep 8
docker logs --tail 8 "$CONTAINER" 2>&1
echo
if docker ps --filter "name=$CONTAINER" --filter "status=running" -q | grep -q .; then
  echo "🎉 Le watchdog tourne ! Il redémarrera tout seul avec Docker Desktop."
  echo "   Pense à cocher « Start Docker Desktop when you sign in » dans les réglages de Docker."
else
  echo "❌ Le watchdog s'est arrêté : regarde les messages ci-dessus (code de connexion ?)."
fi
finish 0
