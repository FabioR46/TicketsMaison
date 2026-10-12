@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title Tickets Maison - Installation du watchdog
cd /d "%~dp0"
set "CONTAINER=tickets-maison-watchdog"

echo ===============================================
echo    Tickets Maison - Installation du watchdog
echo ===============================================
echo.

rem 1. Docker installé ?
where docker >nul 2>&1
if errorlevel 1 (
  echo [X] Docker Desktop n'est pas installé.
  echo     La page de téléchargement va s'ouvrir : installe-le, ouvre-le une fois,
  echo     puis relance ce fichier.
  start "" "https://www.docker.com/products/docker-desktop/"
  goto :fin
)

rem 2. Docker démarré ?
docker info >nul 2>&1
if not errorlevel 1 goto :docker_ok
echo Démarrage de Docker Desktop...
if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
set /a TRIES=0
:attente
timeout /t 3 /nobreak >nul
docker info >nul 2>&1
if not errorlevel 1 goto :docker_ok
set /a TRIES+=1
if !TRIES! lss 60 goto :attente
echo [X] Docker ne répond pas. Ouvre Docker Desktop, attends qu'il soit prêt, puis relance ce fichier.
goto :fin

:docker_ok
echo [OK] Docker est prêt.
echo.

rem 3. Code de connexion
set "CODE="
if exist ".env" (
  for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if /i "%%A"=="TM_CODE" set "OLD=%%B"
  )
  if defined OLD if "!OLD:~0,4!"=="TM1:" (
    set /p "KEEP=Une configuration existe déjà. La garder ? (O/n) "
    if /i not "!KEEP!"=="n" set "CODE=!OLD!"
  )
)

:demande
if defined CODE goto :ecrire

rem Code déjà copié (ex. depuis le mail envoyé par l'app) : on le propose directement
set "CLIP="
for /f "usebackq delims=" %%C in (`powershell -NoProfile -Command "(Get-Clipboard) -join ''"`) do set "CLIP=%%C"
if defined CLIP set "CLIP=!CLIP: =!"
if defined CLIP if "!CLIP:~0,4!"=="TM1:" (
  echo Code de connexion trouvé dans le presse-papiers : !CLIP:~0,14!...
  set /p "USECLIP=L'utiliser ? (O/n) "
  if /i not "!USECLIP!"=="n" (
    set "CODE=!CLIP!"
    goto :ecrire
  )
)

echo Dans l'app Tickets Maison :
echo   Réglages ^> Paramètres de la maison ^> Appareils ^> « Envoyer le code au PC »
echo   (envoie-le par mail, ouvre le mail sur ce PC et copie le code)
echo.
set /p "CODE=Colle le code ici (clic droit) puis Entrée : "
set "CODE=!CODE: =!"
if not "!CODE:~0,4!"=="TM1:" (
  echo [?] Ce n'est pas un code valide (il commence par TM1:^). Réessaie.
  echo.
  set "CODE="
  goto :demande
)

:ecrire
(
  echo TM_CODE=!CODE!
  echo INTERVAL=60
  echo FAILS=3
  echo TIMEOUT=3
  echo TZ=Europe/Paris
) > ".env"

rem 4. Construction + démarrage
echo.
echo Installation (la première fois : 1 à 2 minutes)...
docker compose up -d --build
if errorlevel 1 (
  echo [X] L'installation a échoué (voir les messages ci-dessus^).
  goto :fin
)

echo.
echo Vérification...
timeout /t 8 /nobreak >nul
docker logs --tail 8 %CONTAINER%
echo.
docker ps --filter "name=%CONTAINER%" --filter "status=running" -q | findstr . >nul
if errorlevel 1 (
  echo [X] Le watchdog s'est arrêté : regarde les messages ci-dessus ^(code de connexion ?^).
) else (
  echo [OK] Le watchdog tourne. Il redémarrera tout seul avec Docker Desktop.
  echo      Vérifie que « Start Docker Desktop when you sign in » est coché dans Docker.
)

:fin
echo.
pause
