# Schoenbech Outreach Platform — Invio massivo

App separata (FastAPI + SQLAlchemy + PostgreSQL) per l'**invio email massivo**
a contatti HR: campagne, import liste, bozze personalizzate, invio, recall.

## Separazione da `cv-scouting-lusha`
Usa **lo stesso database** (Cloud SQL `outreach-pg`) ma in uno **schema dedicato `mass`**.
NON tocca né il codice né le tabelle `outreach_*` dell'app esistente (invio CV blind).

- Istanza: `outreach-pg` (`synergyhr-xaeq7:europe-west1:outreach-pg`)
- Schema app: `mass` — tabelle: `company`, `contact`, `campaign`, `campaign_company`,
  `outreach_message`, `outreach_event`, `follow_up`, `suppression`

## Funzioni
- Login (password da Secret Manager `OUTREACH_ADMIN_PASSWORD`)
- Campagne + import `.xlsx`/`.csv` (riconosce le colonne)
- Bozze con personalizzazione (`contesto`, `gancio`, `timing`, `flag`), stato Bozza/Pronta/Esclusa
- **Invio**: Gmail/Aruba SMTP, ritmo umano 65–115s + pausa ogni 10, copia in Posta inviata (IMAP),
  stop su 5.4.5, salvataggio messaggi/eventi nel DB
- **Recall**: contatti inviati da >7 giorni senza risposta, oggetto `RE: …`, stesso motore

## Avvio locale
Doppio clic su `C:\Users\Luca R\Desktop\OUTREACH_MASSIVO.bat`
(avvia il Cloud SQL Proxy se serve, apre `http://127.0.0.1:8788`).

## Deploy online — FATTO ✅
- **URL**: https://outreach-massivo-998063536756.europe-west1.run.app
- Servizio Cloud Run `outreach-massivo`, `europe-west1`
- Cloud SQL via socket (`--add-cloudsql-instances`), secret da Secret Manager
- Re-deploy: `deploy_cloud_run.bat`

## Stato
- [x] Connessione DB + schema `mass`
- [x] Login, campagne, import, bozze, anteprima
- [x] Invio (SMTP + copia Sent + DB)
- [x] Recall (+7 giorni)
- [x] Dockerfile + script deploy
- [x] **Deploy online su Cloud Run** (URL sopra)
