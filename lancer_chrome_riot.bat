@echo off
title Chrome Pilotable par RIOT (Profil Principal)
echo =========================================================
echo   Lancement de votre Google Chrome habituel pour RIOT
echo =========================================================
echo.

set CHROME_EXE=""
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    set CHROME_EXE="C:\Program Files\Google\Chrome\Application\chrome.exe"
) else if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
    set CHROME_EXE="C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
) else if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" (
    set CHROME_EXE="%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
)

if %CHROME_EXE%=="" (
    echo [ERREUR] Impossible de trouver Google Chrome sur cet ordinateur.
    pause
    exit /b 1
)

echo Demarrage de Google Chrome avec vos onglets habituels et port de controle 9222...
start "" %CHROME_EXE% --remote-debugging-port=9222 --restore-last-session --start-maximized
echo.
echo [OK] Chrome est connecte et pret ! Vos onglets et comptes existants sont accessibles.
timeout /t 3 >nul
