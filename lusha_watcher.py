# -*- coding: utf-8 -*-
"""Sorveglia la cartella Download: appena scarichi un file Lusha, lo importa.

Nessuna azione manuale: il file viene letto, normalizzato e inviato all'app
(con AI automatica). Poi viene spostato in <cartella>/_importati per non
reimportarlo.

Configurabile da .env o ambiente:
  OUTREACH_WATCH_DIR       (default: C:\\Users\\<utente>\\Downloads)
  OUTREACH_WATCH_PATTERN   (default: "lusha" - nome file da riconoscere)
  OUTREACH_CAMPAGNA        (default: "Da rivedere")
  OUTREACH_AUTO_AI         ("0" per non lanciare l'AI)
  OUTREACH_URL             (default: servizio cloud)
I file già presenti all'avvio vengono IGNORATI (solo quelli nuovi).
"""
import glob
import os
import shutil
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
from app import config
from app.email_builder import dividi_nome
from app.main import parse_uploaded

# App LOCALE (stessa base dati del cloud): l'AI in background qui non viene
# interrotta dallo spegnimento dell'istanza cloud.
URL = os.environ.get("OUTREACH_URL", "http://127.0.0.1:8788").rstrip("/")
CAMPAGNA = os.environ.get("OUTREACH_CAMPAGNA", "Da rivedere")
AUTO_AI = os.environ.get("OUTREACH_AUTO_AI", "1") != "0"
WATCH_DIR = os.environ.get("OUTREACH_WATCH_DIR", os.path.join(os.path.expanduser("~"), "Downloads"))
PATTERN = os.environ.get("OUTREACH_WATCH_PATTERN", "lusha").lower()
DONE_DIR = os.path.join(WATCH_DIR, "_importati")
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lusha_watch.log")
BATCH = 20
AVVIO = time.time()


def log(msg):
    riga = f"{datetime.now().strftime('%d/%m/%Y %H:%M:%S')} | {msg}"
    try:
        print(riga, flush=True)
    except Exception:
        pass  # pythonw non ha console
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(riga + "\n")
    except Exception:
        pass


def candidati():
    out = []
    for ext in ("*.xlsx", "*.xls", "*.csv"):
        out.extend(glob.glob(os.path.join(WATCH_DIR, ext)))
    return [p for p in out
            if PATTERN in os.path.basename(p).lower()
            and os.path.isfile(p) and os.path.getsize(p) > 1000
            and os.path.getmtime(p) >= AVVIO - 5]


def importa(percorso, token):
    with open(percorso, "rb") as f:
        righe = parse_uploaded(f.read(), os.path.basename(percorso))
    contatti = []
    for r in righe:
        if not (r.get("azienda") and r.get("email")):
            continue
        nome, cognome = dividi_nome(r.get("contatto") or "")
        c = {"azienda": r["azienda"], "email": r["email"], "nome": nome, "cognome": cognome}
        for chiave, dest in (("contesto", "contesto"), ("gancio", "gancio"),
                             ("tecnologia", "tecnologia"), ("appiglio", "appiglio"),
                             ("ricerca_attivita", "attivita"),
                             ("ricerca_competenze", "competenze"),
                             ("ricerca_segnale", "segnale"),
                             ("alert_text", "alert"), ("timing", "timing")):
            valore = (r.get(chiave) or "").strip()
            if valore:
                c[dest] = valore
        contatti.append(c)
    if not contatti:
        return 0, len(righe)
    salvati = 0
    for i in range(0, len(contatti), BATCH):
        r = requests.post(URL + "/api/contatti",
                          json={"campagna": CAMPAGNA, "auto_ai": AUTO_AI,
                                "contatti": contatti[i:i + BATCH]},
                          headers={"X-API-Token": token}, timeout=120)
        if r.status_code != 200:
            raise RuntimeError(f"{r.status_code} {r.text[:120]}")
        salvati += (r.json() or {}).get("salvati", 0)
    return salvati, len(righe) - len(contatti)


def main():
    token = (config.SCHEDULER_TOKEN or "").strip()
    if not token:
        log("ERRORE: SCHEDULER_TOKEN mancante nel .env — watcher non avviato.")
        return
    if not os.path.isdir(WATCH_DIR):
        log(f"ERRORE: cartella non trovata: {WATCH_DIR}")
        return
    os.makedirs(DONE_DIR, exist_ok=True)
    log(f"Watcher avviato | cartella: {WATCH_DIR} | filtro: '{PATTERN}' | campagna: {CAMPAGNA} | AI: {AUTO_AI}")
    visti = set()
    dimensioni = {}
    while True:
        try:
            for p in candidati():
                if p in visti:
                    continue
                dim = os.path.getsize(p)
                if dimensioni.get(p) != dim:
                    dimensioni[p] = dim
                    continue  # file ancora in scrittura: aspetta il giro dopo
                try:
                    salvati, scartati = importa(p, token)
                except Exception as e:
                    log(f"ERRORE su {os.path.basename(p)}: {e} (riprovo se il file resta)")
                    continue
                nome = datetime.now().strftime("%Y%m%d_%H%M%S_") + os.path.basename(p)
                try:
                    shutil.move(p, os.path.join(DONE_DIR, nome))
                except Exception as e:
                    log(f"  importato ma non archiviato ({e})")
                log(f"IMPORTATO {os.path.basename(p)}: salvati {salvati}, scartati {scartati}"
                    + (" (AI in background)" if AUTO_AI else ""))
                visti.add(p)
        except Exception as e:
            log(f"ERRORE nel ciclo: {e}")
        time.sleep(15)


if __name__ == "__main__":
    main()
