@echo off
rem Builds dist\LegacyPlayer\ (LegacyPlayer.exe plus its _internal folder; no Python needed to run it).
rem It is a folder, not one file, so nothing is unpacked into %TEMP% when it starts.
rem Needs Python 3.13 or newer from python.org (tick "Add to PATH"). Run this from the repo folder.
setlocal
cd /d "%~dp0"
if not "%LP_LOGGED%"=="" goto :build
set LP_LOGGED=1
call "%~f0" %* > build.log 2>&1
set RC=%ERRORLEVEL%
type build.log
rem Optional: sign the exe so Windows SmartScreen trusts it. Set LP_SIGN_PFX (certificate file) and LP_SIGN_PASS first.
if "%RC%"=="0" if defined LP_SIGN_PFX signtool sign /f "%LP_SIGN_PFX%" /p "%LP_SIGN_PASS%" /fd sha256 /tr http://timestamp.digicert.com /td sha256 "dist\LegacyPlayer\LegacyPlayer.exe" || set RC=1
echo.
if not "%RC%"=="0" echo BUILD FAILED. The full output was saved to build.log in this folder.
pause
exit /b %RC%
:build
python --version || (echo Python was not found. Install Python 3.13+ from python.org and try again. & exit /b 1)
rem A running copy locks dist\LegacyPlayer ("Access is denied"), so close it first.
taskkill /f /t /im LegacyPlayer.exe
rem If you ran the built app from dist\LegacyPlayer, its files (LegacyPlayerData, data-location.txt) are kept aside and
rem put back after the build: PyInstaller replaces the whole folder.
set KEEP=dist\LegacyPlayer.keep
if exist "%KEEP%" rmdir /s /q "%KEEP%"
mkdir "%KEEP%" >nul 2>&1
if exist dist\LegacyPlayer\LegacyPlayerData move /y dist\LegacyPlayer\LegacyPlayerData "%KEEP%\LegacyPlayerData" >nul || (echo dist\LegacyPlayer\LegacyPlayerData is in use. Close Legacy Player and try again. & exit /b 1)
if exist dist\LegacyPlayer\data-location.txt move /y dist\LegacyPlayer\data-location.txt "%KEEP%\data-location.txt" >nul
for /d %%D in (dist\LegacyPlayer.old-*) do rmdir /s /q "%%D" >nul 2>&1
if exist dist\LegacyPlayer.exe del /f /q dist\LegacyPlayer.exe >nul 2>&1
if exist dist\LegacyPlayer rmdir /s /q dist\LegacyPlayer
rem Windows lets a folder in use be renamed even though it can not be deleted, so move a stubborn one aside.
if exist dist\LegacyPlayer move /y dist\LegacyPlayer dist\LegacyPlayer.old-%RANDOM% >nul
if exist dist\LegacyPlayer (
  echo dist\LegacyPlayer can not be removed or renamed. Something still holds it:
  tasklist /fi "imagename eq LegacyPlayer.exe"
  echo Quit Legacy Player from the tray icon, or end LegacyPlayer.exe in Task Manager ^(run this window as administrator if it was started that way^), then run this again.
  call :restore
  exit /b 1
)
python -m pip install --upgrade pip pyinstaller==6.22.3 psutil==7.2.2 || (call :restore & exit /b 1)
python -m PyInstaller --noconfirm --clean --onedir --windowed --name LegacyPlayer --icon "launcher\ui\legacy-player.ico" ^
  --paths . ^
  --add-data "launcher\ui;launcher\ui" ^
  --collect-submodules launcher --collect-submodules server ^
  --collect-submodules adapters --collect-submodules runtime --collect-submodules frontend ^
  --hidden-import tkinter --hidden-import psutil --collect-submodules tools --add-data "game_packs;game_packs" ^
  legacy_player_app.py || (call :restore & exit /b 1)
call :restore
if not exist dist\LegacyPlayer\LegacyPlayer.exe (echo The build made no dist\LegacyPlayer\LegacyPlayer.exe. & exit /b 1)
if not exist dist\LegacyPlayer\_internal (echo The build made no dist\LegacyPlayer\_internal folder. & exit /b 1)
echo.
for /d %%D in (dist\LegacyPlayer.old-*) do rmdir /s /q "%%D" >nul 2>&1
echo Built: %CD%\dist\LegacyPlayer\LegacyPlayer.exe
echo Double-click it to open Legacy Player. Your files are kept in %CD%\dist\LegacyPlayer\LegacyPlayerData
echo (or the folder you choose in the app: Settings ^> Where Legacy Player keeps its files).
endlocal
exit /b 0

:restore
if not exist dist\LegacyPlayer mkdir dist\LegacyPlayer
if exist "%KEEP%\LegacyPlayerData" move /y "%KEEP%\LegacyPlayerData" dist\LegacyPlayer\LegacyPlayerData >nul
if exist "%KEEP%\data-location.txt" move /y "%KEEP%\data-location.txt" dist\LegacyPlayer\data-location.txt >nul
rmdir "%KEEP%" >nul 2>&1
exit /b 0
