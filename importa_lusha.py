# -*- coding: utf-8 -*-
"""Importa un file Lusha (.xlsx/.csv) nell'app: crea le righe e lancia l'AI.

Uso:
  - trascina il file sopra importa_lusha.bat, oppure
  - py importa_lusha.py "C:\\...\\lusha.xlsx" ["Campagna"]

Variabili facoltative nel .env o nell'ambiente:
  OUTREACH_URL       (default: servizio cloud)
  OUTREACH_CAMPAGNA  (default: "Da rivedere")
  OUTREACH_AUTO_AI   ("0" per non lanciare l'AI)
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
from app import config
from app.email_builder import dividi_nome
from app.main import parse_uploaded

URL = os.environ.get(
    "OUTREACH_URL",
    "https://outreach-massivo-998063536756.europe-west1.run.app").rstrip("/")
CAMPAGNA = os.environ.get("OUTREACH_CAMPAGNA", "Da rivedere")
AUTO_AI = os.environ.get("OUTREACH_AUTO_AI", "1") != "0"
BATCH = 20


def _pausa():
    try:
        input("\nPremi Invio per chiudere...")
    except EOFError:
        pass


def main():
    if len(sys.argv) < 2:
        print("Trascina qui il file Lusha (.xlsx/.csv) oppure:")
        print('  py importa_lusha.py "percorso\\file.xlsx" ["Campagna"]')
        _pausa()
        return
    percorso = sys.argv[1]
    campagna = sys.argv[2] if len(sys.argv) > 2 else CAMPAGNA
    token = (config.SCHEDULER_TOKEN or "").strip()
    if not token:
        print("Manca SCHEDULER_TOKEN nel file .env (lo trovi nella pagina API dell'app).")
        _pausa()
        return

    with open(percorso, "rb") as f:
        righe = parse_uploaded(f.read(), os.path.basename(percorso))
    print(f"Righe lette da {os.path.basename(percorso)}: {len(righe)}")

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

    print(f"Contatti validi (azienda+email): {len(contatti)} | scartati: {len(righe) - len(contatti)}")
    if not contatti:
        print("Niente da importare.")
        _pausa()
        return

    salvati = scartati = 0
    for i in range(0, len(contatti), BATCH):
        blocco = contatti[i:i + BATCH]
        payload = {"campagna": campagna, "auto_ai": AUTO_AI, "contatti": blocco}
        try:
            r = requests.post(URL + "/api/contatti", json=payload,
                              headers={"X-API-Token": token}, timeout=120)
            dati = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if r.status_code == 200 and dati.get("ok"):
                salvati += dati.get("salvati", 0)
                scartati += dati.get("scartati", 0)
                print(f"  blocco {i // BATCH + 1}: salvati {dati.get('salvati')}")
            else:
                print(f"  blocco {i // BATCH + 1}: ERRORE {r.status_code} {r.text[:150]}")
        except Exception as e:
            print(f"  blocco {i // BATCH + 1}: ERRORE {e}")

    print(f"\nFatto: {salvati} contatti in '{campagna}'"
          + (" (l'AI sta generando in background)" if AUTO_AI else "")
          + f". Scartati: {scartati}.")
    _pausa()


if __name__ == "__main__":
    main()
