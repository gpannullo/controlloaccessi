@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy-server.ps1" %*
set "DEPLOY_RESULT=%ERRORLEVEL%"
echo.
if not "%DEPLOY_RESULT%"=="0" (
    echo DEPLOY INTERROTTO. Leggere l'errore sopra. Nessun rollback automatico delle migrazioni.
    echo La finestra restera aperta per consentire la lettura dell'errore.
    pause
) else (
    echo Deploy completato correttamente. Chiusura automatica tra 5 secondi...
    timeout /t 5 /nobreak >nul
)
exit /b %DEPLOY_RESULT%
