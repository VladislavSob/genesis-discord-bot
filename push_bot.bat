@echo off
chcp 65001 >nul
cd C:\Users\Genesis\Downloads\Genesis_BOT

echo ==============================
echo  Проверка Git-репозитория...
echo ==============================

REM init при необходимости
if not exist .git (
  git init
)

REM remote origin при необходимости
git remote get-url origin >nul 2>&1
if errorlevel 1 (
  git remote add origin https://github.com/VladislavSob/genesis-discord-bot.git
)

REM гарантируем ветку main
for /f "tokens=*" %%i in ('git branch --show-current') do set BR=%%i
if "%BR%"=="" git branch -M main

echo.
set /p MSG=Сообщение коммита (можно по-русски): 
if "%MSG%"=="" set MSG=Обновление кода бота

echo.
echo Добавляю изменения...
git add .

echo Делаю коммит...
git commit -m "%MSG%" || echo Нет изменений для коммита.

echo Отправляю на GitHub...
git push -u origin main

echo.
echo ==============================
echo  Готово! Код отправлен :)
echo ==============================
pause
