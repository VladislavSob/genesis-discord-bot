@echo off
cd C:\Users\Genesis\Downloads\Genesis_BOT

echo ==============================
echo   Проверка Git-репозитория...
echo ==============================

REM Проверяем, инициализирован ли git
if not exist .git (
    echo Git-репозиторий не найден. Инициализирую...
    git init
)

REM Проверяем, есть ли remote "origin"
git remote get-url origin >nul 2>&1
if errorlevel 1 (
    echo Remote origin не найден. Добавляю...
    git remote add origin https://github.com/VladislavSob/genesis-discord-bot.git
)

REM Проверяем, есть ли ветка main
for /f "tokens=*" %%i in ('git branch --show-current') do set BRANCH=%%i
if "%BRANCH%"=="" (
    echo Ветка не выбрана. Устанавливаю main...
    git branch -M main
)

echo ==============================
echo   Добавляю изменения...
echo ==============================
git add .

echo ==============================
echo   Делаю коммит...
echo ==============================
git commit -m "Авто-обновление кода бота" || echo Нет изменений для коммита.

echo ==============================
echo   Отправляю на GitHub...
echo ==============================
git push -u origin main

echo ==============================
echo   Готово! Код отправлен :)
echo ==============================
pause
