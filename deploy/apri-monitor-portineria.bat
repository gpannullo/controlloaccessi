@echo off
setlocal

REM Inserire qui il valore di PUBLIC_MONITOR_TOKEN configurato sul server.
set "MONITOR_TOKEN=INSERIRE_IL_TOKEN"

REM Coordinate del monitor secondario: a sinistra di uno schermo 1920px.
REM Per metterlo a destra usare 1920,0.
set "SECONDARY_X=-1920"
set "SECONDARY_Y=0"

set "MONITOR_URL=https://controlloaccessi.comune.aversa.ce.it/monitor/pubblico/%MONITOR_TOKEN%/"
set "PROFILE_DIR=%LOCALAPPDATA%\ControlloAccessiMonitor"

if not "%MONITOR_TOKEN%"=="INSERIRE_IL_TOKEN" goto apri

echo Configurare MONITOR_TOKEN prima di avviare il monitor.
pause
exit /b 1

:apri
if exist "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" (
    start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --kiosk --new-window --user-data-dir="%PROFILE_DIR%" --window-position=%SECONDARY_X%,%SECONDARY_Y% "%MONITOR_URL%"
    exit /b 0
)

if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --kiosk --new-window --user-data-dir="%PROFILE_DIR%" --window-position=%SECONDARY_X%,%SECONDARY_Y% "%MONITOR_URL%"
    exit /b 0
)

echo Non sono stati trovati Microsoft Edge o Google Chrome nei percorsi previsti.
pause
exit /b 1
