@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy-server.ps1" %*
set "DEPLOY_RESULT=%ERRORLEVEL%"
echo.
if not "%DEPLOY_RESULT%"=="0" echo DEPLOY INTERROTTO. Leggere l'errore sopra. Nessun rollback automatico delle migrazioni.
pause
exit /b %DEPLOY_RESULT%
