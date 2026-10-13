@echo off
REM ============================================================
REM  Avvio locale Outreach Schoenbech (proxy database + app)
REM  Idempotente: avvia solo i pezzi mancanti.
REM ============================================================

powershell -NoProfile -ExecutionPolicy Bypass -Command "if (-not (Test-NetConnection 127.0.0.1 -Port 5432 -InformationLevel Quiet -WarningAction SilentlyContinue)) { Start-Process -FilePath 'C:\Users\Luca R\outreach-platform\tools\cloud-sql-proxy.exe' -ArgumentList 'synergyhr-xaeq7:europe-west1:outreach-pg','--port','5432' -WindowStyle Hidden }"

ping -n 9 127.0.0.1 >nul

powershell -NoProfile -ExecutionPolicy Bypass -Command "if (-not (Test-NetConnection 127.0.0.1 -Port 8788 -InformationLevel Quiet -WarningAction SilentlyContinue)) { Start-Process -FilePath 'C:\Users\Luca R\AppData\Local\Python\pythoncore-3.14-64\python.exe' -ArgumentList '-m','app.main' -WorkingDirectory 'C:\Users\Luca R\outreach-platform' -WindowStyle Hidden }"
