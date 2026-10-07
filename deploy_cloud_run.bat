@echo off
REM ============================================================
REM  Deploy su Cloud Run — Outreach Massivo (Schoenbech)
REM  NON eseguito automaticamente: lanciare solo su richiesta.
REM ============================================================
REM  Prerequisiti (una volta):
REM   1) Creare i secret SMTP (se non esistono):
REM      gcloud secrets create OUTREACH_SMTP_PASSWORD --data-file=- < file
REM      gcloud secrets create OUTREACH_ARUBA_PASSWORD --data-file=- < file
REM   2) Autenticazione: gcloud auth login
REM ============================================================

set PROJECT=synergyhr-xaeq7
set REGION=europe-west1
set SERVICE=outreach-massivo
set INSTANCE=synergyhr-xaeq7:europe-west1:outreach-pg

gcloud config set project %PROJECT%

gcloud run deploy %SERVICE% ^
  --source . ^
  --region %REGION% ^
  --allow-unauthenticated ^
  --add-cloudsql-instances %INSTANCE% ^
  --set-secrets "DATABASE_URL=OUTREACH_DATABASE_URL:latest,SECRET_KEY=OUTREACH_SESSION_SECRET:latest,ADMIN_PASSWORD=OUTREACH_ADMIN_PASSWORD:latest,SMTP_PASSWORD=OUTREACH_SMTP_PASSWORD:latest,ARUBA_PASSWORD=OUTREACH_ARUBA_PASSWORD:latest" ^
  --set-env-vars "DB_SCHEMA=mass,SENDER_EMAIL=luca@schoenbech.com,REPLY_TO=luca@schoenbech.com,SMTP_SERVER=smtp.gmail.com,SMTP_PORT=465,IMAP_SERVER=imap.gmail.com,IMAP_PORT=993,ARUBA_SMTP_SERVER=smtps.aruba.it,ARUBA_SMTP_PORT=465,ARUBA_IMAP_SERVER=imaps.aruba.it,ARUBA_IMAP_PORT=993,ARUBA_EMAIL=luca@schoenbech.com,DELAY_MIN=65,DELAY_MAX=115,BREAK_MIN=150,BREAK_MAX=240,PAUSE_EVERY=10"

echo.
echo Deploy completato. URL del servizio:
gcloud run services describe %SERVICE% --region %REGION% --format="value(status.url)"
pause
