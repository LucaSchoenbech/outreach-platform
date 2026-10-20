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

## Invio programmato (anche a computer spento)

Su Cloud Run il servizio viene spento quando nessuno lo usa (`--min-instances 0`,
`--cpu-throttling`), quindi un invio lungo in un processo di sfondo non
arriverebbe in fondo. L'invio programmato e' guidato dall'esterno: **Cloud
Scheduler chiama `/scheduler/tick` ogni due minuti dentro la finestra oraria, e
ogni chiamata spedisce al piu' una email**. Il ritmo umano resta quello
configurato (`DELAY_MIN`..`DELAY_MAX`, pausa ogni `PAUSE_EVERY`): l'attesa e'
custodita nella tabella `scheduler_state` invece che in un `sleep`.

Dalla pagina Invio o Richiami della campagna si preme *Programma invii/richiami
automatici*. Si puo' fare la sera per il mattino dopo. Quando non restano righe
da inviare il flag si spegne da solo.

### Impostazione, una volta sola

I comandi qui sotto sono nella forma del Prompt dei comandi, dove `^` spezza
le righe. **In PowerShell quel carattere non funziona**: incolla ogni comando
su una riga sola, oppure usa l'apice inverso al posto di `^`.

```bat
REM 1) un segreto lungo e casuale, condiviso fra servizio e scheduler
powershell -Command "[guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')" > token.txt
gcloud secrets create OUTREACH_SCHEDULER_TOKEN --data-file=token.txt
del token.txt

REM 2) pubblica il servizio, che ora riceve il segreto
deploy_cloud_run.bat

REM 3) il lavoro programmato: ogni 2 minuti, 09:25-12:00, ora italiana
gcloud scheduler jobs create http outreach-tick ^
  --location europe-west1 ^
  --schedule "*/2 9-11 * * 1-5" ^
  --time-zone "Europe/Rome" ^
  --uri "https://outreach-massivo-998063536756.europe-west1.run.app/scheduler/tick" ^
  --http-method POST ^
  --headers "X-Scheduler-Token=IL_TUO_SEGRETO"
```

Cloud Scheduler offre 3 lavori gratuiti al mese e il servizio si sveglia solo
per quelle chiamate, che durano meno di un secondo quando non c'e' nulla da
spedire.

Senza `SCHEDULER_TOKEN` configurato l'indirizzo risponde 503 e non spedisce
nulla: e' chiuso per difetto.

## Stato
- [x] Connessione DB + schema `mass`
- [x] Login, campagne, import, bozze, anteprima
- [x] Invio (SMTP + copia Sent + DB)
- [x] Recall (+7 giorni)
- [x] Dockerfile + script deploy
- [x] **Deploy online su Cloud Run** (URL sopra)
