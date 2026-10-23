# -*- coding: utf-8 -*-
"""Sorveglia la cartella Download e importa i file Lusha appena compaiono.

Nessuna azione manuale: legge, normalizza, invia all'app (AI inclusa) e archivia
il file in <cartella>/_importati. Gestisce i casi noti:
- file con nome diverso ma con intestazioni da lista contatti (sniff colonne)
- file scaricati mentre il watcher era spento (finestra di 24 ore)
- app locale spenta (prova a riavviarla, con attesa fra i tentativi)
- file che non si riescono a importare (dopo 5 tentativi -> _da_verificare)

Configurabile da .env o ambiente:
  OUTREACH_WATCH_DIR       (default: ~/Downloads)
  OUTREACH_WATCH_PATTERN   (default: "lusha")
  OUTREACH_WATCH_HOURS     (default: 24 - quanti file recenti guardare)
  OUTREACH_CAMPAGNA        (default: "Da rivedere")
  OUTREACH_AUTO_AI         ("0" per non lanciare l'AI)
  OUTREACH_URL             (default: http://127.0.0.1:8788, app locale)
"""
import glob
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import requests
from app import config
from app.email_builder import dividi_nome
from app.main import parse_uploaded

BASE = os.path.dirname(os.path.abspath(__file__))
URL = os.environ.get("OUTREACH_URL", "http://127.0.0.1:8788").rstrip("/")
CAMPAGNA = os.environ.get("OUTREACH_CAMPAGNA", "Da rivedere")
AUTO_AI = os.environ.get("OUTREACH_AUTO_AI", "1") != "0"
WATCH_DIR = os.environ.get("OUTREACH_WATCH_DIR", os.path.join(os.path.expanduser("~"), "Downloads"))
PATTERN = os.environ.get("OUTREACH_WATCH_PATTERN", "lusha").lower()
try:
    ORE = float(os.environ.get("OUTREACH_WATCH_HOURS", "24"))
except ValueError:
    ORE = 24.0
DONE_DIR = os.path.join(WATCH_DIR, "_importati")
ERR_DIR = os.path.join(WATCH_DIR, "_da_verificare")
LOG = os.path.join(BASE, "lusha_watch.log")
BATCH = 20
MAX_TENTATIVI = 5
CREA_NO_WINDOW = 0x08000000


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


def intestazioni(percorso):
    try:
        if percorso.lower().endswith(".csv"):
            df = pd.read_csv(percorso, nrows=2, header=None, dtype=str,
                             sep=None, engine="python")
        else:
            df = pd.read_excel(percorso, nrows=2, header=None, dtype=str)
        return [str(x).strip() for x in df.iloc[0].tolist()] if len(df) else []
    except Exception:
        return []


def sembra_lusha(colonne):
    c = [str(x).lower() for x in colonne]
    ha_email = any(("email" in x) or ("e-mail" in x) or (x.strip() == "mail") for x in c)
    ha_nome_o_azienda = any(("first name" in x) or ("last name" in x) or ("full name" in x)
                            or ("company" in x) or (x.strip() in ("nome", "cognome", "azienda",
                                                                  "contatto", "societa"))
                            for x in c)
    return ha_email and ha_nome_o_azienda


def nuovi_file(sniffati):
    out = []
    limite = time.time() - ORE * 3600
    for ext in ("*.xlsx", "*.xls", "*.csv"):
        for p in glob.glob(os.path.join(WATCH_DIR, ext)):
            try:
                if not os.path.isfile(p) or os.path.getsize(p) < 1000:
                    continue
                if os.path.getmtime(p) < limite:
                    continue
                nome = os.path.basename(p).lower()
                if PATTERN in nome:
                    out.append(p)
                    continue
                if p not in sniffati:
                    sniffati[p] = sembra_lusha(intestazioni(p))
                if sniffati[p]:
                    out.append(p)
            except OSError:
                continue
    return out


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


def archivia(percorso, cartella):
    os.makedirs(cartella, exist_ok=True)
    nome = datetime.now().strftime("%Y%m%d_%H%M%S_") + os.path.basename(percorso)
    try:
        shutil.move(percorso, os.path.join(cartella, nome))
        return True
    except Exception as e:
        log(f"  non archiviato ({e})")
        return False


def main():
    token = (config.SCHEDULER_TOKEN or "").strip()
    if not token:
        log("ERRORE: SCHEDULER_TOKEN mancante nel .env — watcher non avviato.")
        return
    if not os.path.isdir(WATCH_DIR):
        log(f"ERRORE: cartella non trovata: {WATCH_DIR}")
        return
    os.makedirs(DONE_DIR, exist_ok=True)
    os.makedirs(ERR_DIR, exist_ok=True)
    log(f"Watcher avviato | cartella: {WATCH_DIR} | nome contiene: '{PATTERN}' (o colonne da lista contatti) | "
        f"ultime {ORE:g}h | campagna: {CAMPAGNA} | AI: {AUTO_AI}")
    elaborati = set()
    dimensioni = {}
    tentativi = {}
    sniffati = {}
    ultimo_riavvio = 0.0
    while True:
        try:
            for p in nuovi_file(sniffati):
                if p in elaborati:
                    continue
                dim = os.path.getsize(p)
                if dimensioni.get(p) != dim:
                    dimensioni[p] = dim
                    continue  # file ancora in scrittura
                try:
                    salvati, scartati = importa(p, token)
                except requests.ConnectionError:
                    if time.time() - ultimo_riavvio > 300:
                        ultimo_riavvio = time.time()
                        log("App locale non raggiungibile: provo a riavviarla (proxy + app)...")
                        try:
                            subprocess.run(["cmd", "/c", os.path.join(BASE, "avvia_outreach.bat")],
                                           cwd=BASE, creationflags=CREA_NO_WINDOW, timeout=120)
                        except Exception as e:
                            log(f"  riavvio non riuscito: {e}")
                    continue
                except Exception as e:
                    tentativi[p] = tentativi.get(p, 0) + 1
                    log(f"ERRORE su {os.path.basename(p)} (tentativo {tentativi[p]}/{MAX_TENTATIVI}): {e}")
                    if tentativi[p] >= MAX_TENTATIVI:
                        archivia(p, ERR_DIR)
                        log("  spostato in _da_verificare")
                        elaborati.add(p)
                    continue
                colonne = intestazioni(p) if salvati == 0 else []
                archivia(p, DONE_DIR)
                log(f"IMPORTATO {os.path.basename(p)}: salvati {salvati}, scartati {scartati}"
                    + (" (AI in background)" if AUTO_AI else ""))
                if salvati == 0:
                    log(f"  ATTENZIONE: nessun contatto valido. Colonne lette: {colonne}")
                elaborati.add(p)
        except Exception as e:
            log(f"ERRORE nel ciclo: {e}")
        time.sleep(15)


if __name__ == "__main__":
    main()
