@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Arrêt et suppression du watchdog Tickets Maison...
docker compose down --rmi local 2>nul || docker rm -f tickets-maison-watchdog
echo [OK] Terminé. Tu peux supprimer ce dossier.
pause
