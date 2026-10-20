@echo off
REM ============================================================
REM  Deploy su Cloud Run — Outreach Massivo (Schoenbech)
REM  NON eseguito automaticamente: lanciare solo su richiesta.
REM ============================================================
REM  Prerequisiti (una volta):
REM   1) Creare i secret (se non esistono):
REM      OUTREACH_DATABASE_URL, OUTREACH_SESSION_SECRET, OUTREACH_ADMIN_PASSWORD,
REM      OUTREACH_SMTP_PASSWORD, OUTREACH_ARUBA_PASSWORD,
REM      GEMINI_API_KEY, OUTREACH_DEEPSEEK_API_KEY,
REM      OUTREACH_SCHEDULER_TOKEN  (avvio programmato: vedi README)
REM   2) Autenticazione: gcloud auth login
REM ============================================================

set PROJECT=synergyhr-xaeq7
set REGION=europe-west1
set SERVICE=outreach-massivo
set INSTANCE=synergyhr-xaeq7:europe-west1:outreach-pg

call gcloud config set project %PROJECT%

call gcloud run deploy %SERVICE% ^
  --source . ^
  --region %REGION% ^
  --allow-unauthenticated ^
  --min-instances 0 ^
  --max-instances 1 ^
  --cpu-throttling ^
  --add-cloudsql-instances %INSTANCE% ^
  --set-secrets "DATABASE_URL=OUTREACH_DATABASE_URL:latest,SECRET_KEY=OUTREACH_SESSION_SECRET:latest,ADMIN_PASSWORD=OUTREACH_ADMIN_PASSWORD:latest,SMTP_PASSWORD=OUTREACH_SMTP_PASSWORD:latest,ARUBA_PASSWORD=OUTREACH_ARUBA_PASSWORD:latest,GEMINI_API_KEY=GEMINI_API_KEY:latest,DEEPSEEK_API_KEY=OUTREACH_DEEPSEEK_API_KEY:latest,SCHEDULER_TOKEN=OUTREACH_SCHEDULER_TOKEN:latest" ^
  --env-vars-file "%~dp0cloudrun_env.yaml"

REM Se il deploy e' fallito (permessi su un segreto, build rotta, quota...)
REM fermati qui: annunciare "completato" dopo un errore fa credere che il
REM servizio sia aggiornato quando invece gira ancora la versione precedente.
if errorlevel 1 (
  echo.
  echo *** DEPLOY FALLITO ***
  echo Il servizio NON e' stato aggiornato: gira ancora la versione precedente.
  echo Leggi l'errore qui sopra. Se parla di "Secret Manager Secret Accessor",
  echo manca il permesso di lettura su un segreto.
  pause
  exit /b 1
)

echo.
echo Deploy completato. URL del servizio:
call gcloud run services describe %SERVICE% --region %REGION% --format="value(status.url)"
echo Revisione ora attiva:
call gcloud run services describe %SERVICE% --region %REGION% --format="value(status.latestReadyRevisionName)"
pause
