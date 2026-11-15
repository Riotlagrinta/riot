@echo off
title RIOT - Terminal Copilote
cd /d "%~dp0"
where uv >nul 2>nul
if %errorlevel% equ 0 (
    uv run python riot.py %*
) else if exist "%USERPROFILE%\.local\bin\uv.exe" (
    "%USERPROFILE%\.local\bin\uv.exe" run python riot.py %*
) else (
    python riot.py %*
)
