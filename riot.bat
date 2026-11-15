@echo off
chcp 65001 >nul
title RIOT - Terminal Copilote
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" riot.py %*
) else (
    where uv >nul 2>nul
    if %errorlevel% equ 0 (
        uv run python riot.py %*
    ) else if exist "%USERPROFILE%\.local\bin\uv.exe" (
        "%USERPROFILE%\.local\bin\uv.exe" run python riot.py %*
    ) else (
        python riot.py %*
    )
)
