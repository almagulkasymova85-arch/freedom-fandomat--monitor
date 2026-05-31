@echo off
chcp 65001 >nul
echo.
echo ============================================
echo   Freedom Фандоматы — Настройка Telegram
echo ============================================
echo.

:: Проверяем Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python не найден. Скачайте с https://python.org
    echo    При установке поставьте галочку "Add to PATH"
    pause
    exit /b 1
)

:: Запускаем скрипт
cd /d "%~dp0"
python setup.py

echo.
echo Нажмите любую клавишу для закрытия...
pause >nul
