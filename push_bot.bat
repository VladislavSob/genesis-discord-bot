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

REM определяем текущую ветку
for /f "tokens=*" %%i in ('git branch --show-current') do set CURBR=%%i

REM если ветка пустая (новый репо), делаем main
if "%CURBR%"=="" (
  git checkout -b main
  set CURBR=main
)

echo.
set /p MSG=Сообщение коммита (можно по-русски): 
if "%MSG%"=="" set MSG=Обновление кода бота

echo.
echo Добавляю изменения...
git add .

echo Делаю коммит...
git commit -m "%MSG%" || echo Нет изменений для коммита.

echo Отправляю на GitHub в ветку %CURBR%...
git push -u origin %CURBR%

echo.
echo ==============================
echo  Готово! Код отправлен :)
echo ==============================
pause
