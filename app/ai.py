# -*- coding: utf-8 -*-
"""Generazione AI della personalizzazione (contesto + gancio).

Provider principale: DeepSeek (API OpenAI-compatibile), modello configurabile
(default: deepseek-v4.1-flash). Fallback: Gemini.
Rileva l'esaurimento di quota/credito e lo segnala.
"""
import json
import random
import threading

import requests

from app import config

AI_STATE = {"running": False, "total": 0, "done": 0, "current": "", "error": "",
            "quota": False, "generated": 0, "model": config.DEEPSEEK_MODEL,
            "provider": "DeepSeek"}
AI_LOCK = threading.Lock()
AI_STOP = threading.Event()


# Formule di chiusura usate a rotazione (scarsità attribuita al mercato).
FORMULE = [
    "risultano tra i più complessi da intercettare sul mercato",
    "sono particolarmente contesi",
    "presentano una disponibilità limitata sul mercato",
    "richiedono una ricerca particolarmente mirata",
]


class QuotaExhausted(Exception):
    """Quota/credito API esaurito."""


class AIError(Exception):
    pass


PROMPT = """Sei un Talent Advisor indipendente italiano, specializzato nella ricerca e
valutazione di profili manageriali e specialistici senior. Ricevi i DATI DI RICERCA su
un'azienda target e devi produrre la personalizzazione di una email di outreach in italiano.

La frase che stai completando è:
"mi permetto di scriverLe per presentarmi: sono un Talent Advisor indipendente, specializzato
nella ricerca e valutazione di profili manageriali e specialistici senior, con particolare
attenzione al mondo <CONTESTO>, <GANCIO>."
Il gancio deve PROSEGUIRE la frase in modo naturale, attaccato con una virgola.

OBIETTIVO: il destinatario deve percepire che conosci il suo contesto industriale concreto
(business, prodotti e servizi, presenza e attività in Italia, mercati serviti, tecnologie
e competenze distintive, temi di innovazione, qualità, sostenibilità, automazione, export,
produzione, engineering, regulatory) e che segui personalmente gli incarichi.
La difficoltà di reperimento va attribuita al MERCATO e alla disponibilità dei profili,
MAI al consulente.

Rispondi SOLO con un oggetto JSON con questi campi:
- "contesto": completa "al mondo ...". Inizia con "del ", "della ", "dei ", "delle ",
  "degli " o "dell'"; sintetico, basato sull'attività concreta dell'azienda.
  Massimo 10 parole.
- "gancio": UNA frase (massimo 28 parole) che PROSEGUE la frase precedente con questa
  struttura: "<connettore> <tipologia di profili> con <competenze rilevanti> <chiusura>".
  Connettori ammessi: "dove", "ambiti nei quali", "in cui", "settori in cui",
  "contesti in cui", "una fase in cui". Poi il soggetto (i profili / le competenze).
- "tipo_gancio": uno tra "Scarsità", "Visibilità", "Fase", "Neutro".
- "flag": uno tra "OK", "Correzione", "Verifica", "Sensibile".

PERSONALIZZAZIONE:
- Non limitarti a sostituire il nome del settore: individua 1-2 elementi REALMENTE
  caratterizzanti dai dati e collegali a una plausibile esigenza di talent acquisition,
  citando la tipologia di profili e le competenze rilevanti.
- Esempi:
  "...al mondo delle tecnologie e degli impianti per il packaging, dove profili tecnici
  e commerciali con solide competenze applicative e una buona comprensione delle esigenze
  dei clienti industriali richiedono una ricerca particolarmente mirata."
  "...in contesti farmaceutici ad elevata specializzazione, dove profili tecnici, quality
  e regulatory con esperienza specifica di processo sono particolarmente contesi."
  "...in contesti industriali internazionali, dove profili tecnici e manageriali capaci
  di combinare competenza specialistica, esperienza operativa e capacità di lavorare su
  mercati diversi risultano difficili da intercettare."
- Se le informazioni sono limitate, usa una personalizzazione prudente e credibile,
  senza forzare.

REGOLE TASSATIVE:
- Prima persona singolare e soggetto "il mercato". VIETATI: "lavoriamo", "nella nostra
  esperienza", "il nostro team", "i nostri consulenti", "dal nostro osservatorio",
  e MAI "voi dovreste".
- La scarsità è del MERCATO, mai del consulente. VIETATI: "ho difficoltà a trovare",
  "faccio fatica a reperire", "ho riscontrato difficoltà". Preferisci: "risultano tra i
  più complessi da intercettare sul mercato", "sono particolarmente contesi",
  "presentano una disponibilità limitata sul mercato", "richiedono una ricerca
  particolarmente mirata".
- Se nei DATI è presente il campo "formula", usala come chiusura del gancio
  (adattandola con naturalezza alla frase).
- NON inventare: clienti, incarichi svolti, case history, conoscenza diretta
  dell'azienda, esperienze pregresse con quella società, dati non verificati.
  VIETATI: "conosciamo bene la vostra realtà", "abbiamo seguito aziende simili",
  "la nostra esperienza nel vostro settore".
- VIETATO ripetere parole già presenti nel "contesto" (settore, prodotti, mercato):
  il gancio deve AGGIUNGERE, non rispiegare.
- VIETATO l'assoluto/saccente: "è necessario", "bisogna", "le aziende devono", "serve",
  "occorre"; e le formule deboli o incerte: "ci risulta", "ci sembra", "forse",
  "probabilmente".
- Non spiegare all'azienda il suo business: aggiungi solo un'osservazione di mercato.
- Niente numeri, fatturati, acquisizioni, investimenti, nomi di clienti.
- Tono professionale, senior, asciutto e naturale: non deve sembrare una mail generata
  automaticamente, commerciale aggressiva, autoreferenziale, da grande società di
  executive search o da freelance low cost.
- Una sola frase, semplice e lineare: evita costruzioni contorte o ridondanti.

GUARDRAIL:
- Situazione delicata (ammortizzatori sociali, crisi, discontinuità, fermo produzione,
  ricapitalizzazione) -> "tipo_gancio": "Neutro", gancio neutro, "flag": "Sensibile".
- Timing "BASSO" o con "MONITORARE" -> gancio neutro.
- Timing con "VERIFICARE" -> "flag": "Verifica".
- Alert che corregge il settore (errato/troppo stretto/incompleto) -> "flag": "Correzione".
- Se non c'è materiale sufficiente -> "gancio": "" e "tipo_gancio": "Neutro".

DATI DI RICERCA (JSON):
"""


def _split(v):
    return [x.strip() for x in (v or "").split(",") if x.strip()]


def _call_deepseek(text):
    key = (config.DEEPSEEK_API_KEY or "").strip()
    if not key:
        raise AIError("DEEPSEEK_API_KEY non configurata")
    models = [config.DEEPSEEK_MODEL] + _split(config.DEEPSEEK_MODEL_FALLBACKS)
    last, quota = None, 0
    for model in models:
        try:
            r = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model,
                      "messages": [{"role": "system", "content": PROMPT},
                                   {"role": "user", "content": text}],
                      "response_format": {"type": "json_object"},
                      "temperature": 0.4, "stream": False},
                timeout=120)
        except Exception as e:
            last = f"{model}: {e}"
            continue
        low = r.text.lower()
        if r.status_code in (402, 429) or "insufficient" in low or "quota" in low or "balance" in low:
            quota += 1
            last = "quota"
            continue
        if r.status_code == 200:
            try:
                return json.loads(r.json()["choices"][0]["message"]["content"])
            except Exception as e:
                last = f"{model} parse: {e}"
                continue
        last = f"{model} {r.status_code}: {r.text[:150]}"
    if quota and quota == len(models):
        raise QuotaExhausted("Quota/credito API esaurito (DeepSeek). Riprova più tardi.")
    raise AIError(last or "DeepSeek non disponibile")


def _call_gemini(text):
    key = (config.GEMINI_API_KEY or "").strip()
    if not key:
        raise AIError("GEMINI_API_KEY non configurata")
    models = [config.GEMINI_MODEL] + _split(config.GEMINI_MODEL_FALLBACKS)
    last, quota = None, 0
    for idx, model in enumerate(models):
        gen = {"responseMimeType": "application/json", "temperature": 0.4}
        if idx == 0 and config.GEMINI_THINKING:
            gen["thinkingConfig"] = {"thinkingLevel": config.GEMINI_THINKING}
        payload = {"contents": [{"role": "user", "parts": [{"text": text}]}],
                   "generationConfig": gen}
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={key}")
        try:
            r = requests.post(url, json=payload, timeout=120)
        except Exception as e:
            last = f"{model}: {e}"
            continue
        if r.status_code == 429 or "RESOURCE_EXHAUSTED" in r.text:
            quota += 1
            last = "quota"
            continue
        if r.status_code == 200:
            try:
                return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
            except Exception as e:
                last = f"{model} parse: {e}"
                continue
        last = f"{model} {r.status_code}: {r.text[:150]}"
    if quota and quota == len(models):
        raise QuotaExhausted("Quota API esaurita (Gemini, tier gratuito). Riprova più tardi.")
    raise AIError(last or "Gemini non disponibile")


def generate_personalization(data):
    """Prova DeepSeek, poi Gemini. Ritorna dict {contesto, gancio, tipo_gancio, flag}."""
    text = PROMPT + json.dumps(data, ensure_ascii=False)
    errors = []
    quota_msgs = []
    if config.DEEPSEEK_API_KEY:
        try:
            return _call_deepseek(text)
        except QuotaExhausted as e:
            quota_msgs.append(str(e))
        except Exception as e:
            errors.append(f"DeepSeek: {e}")
    if config.GEMINI_API_KEY:
        try:
            return _call_gemini(text)
        except QuotaExhausted as e:
            quota_msgs.append(str(e))
        except Exception as e:
            errors.append(f"Gemini: {e}")
    if quota_msgs and not errors:
        raise QuotaExhausted(" ".join(quota_msgs))
    raise AIError(" | ".join(errors + quota_msgs) or "nessun provider AI configurato")


def generate_one(cc_id):
    """Rigenera la personalizzazione di un singolo contatto. Ritorna un messaggio."""
    from app import models
    from app.db import SessionLocal
    from app.email_builder import build_apertura
    db = SessionLocal()
    try:
        cc = db.get(models.CampaignCompany, cc_id)
        if not cc:
            return "Contatto non trovato"
        comp = db.get(models.Company, cc.company_id)
        con = db.get(models.Contact, cc.contact_id) if cc.contact_id else None
        data = {"azienda": comp.legal_name if comp else "",
                "attivita": cc.ricerca_attivita or "", "competenze": cc.ricerca_competenze or "",
                "segnale": cc.ricerca_segnale or "", "alert": cc.alert_text or "",
                "timing": cc.timing or ""}
        if not any([data["attivita"], data["competenze"], data["segnale"], data["alert"]]):
            return "Nessun dato di ricerca per questo contatto"
        data["formula"] = random.choice(FORMULE)
        out = generate_personalization(data)
        cc.contesto = (out.get("contesto") or "").strip()
        cc.gancio = (out.get("gancio") or "").strip()
        cc.tipo_gancio = (out.get("tipo_gancio") or "").strip()
        if out.get("flag") in ("OK", "Correzione", "Verifica", "Sensibile"):
            cc.flag = out["flag"]
        cc.paragrafo_apertura = build_apertura(cc.contesto or "", cc.gancio or "")
        em = (con.email if con else "") or ""
        cc.draft_status = "Pronta" if (cc.contesto and cc.gancio and em) else "Bozza"
        db.commit()
        return "Personalizzazione aggiornata"
    except QuotaExhausted as e:
        return str(e)
    except Exception as e:
        return f"Errore: {e}"
    finally:
        db.close()


def run_generate(rows):
    """rows = lista di {cc_id, azienda, data}. Gira in background."""
    from app import models
    from app.db import SessionLocal
    from app.email_builder import build_apertura
    with AI_LOCK:
        AI_STATE.update(running=True, total=len(rows), done=0, current="",
                        error="", quota=False, generated=0)
    db = SessionLocal()
    try:
        for idx, row in enumerate(rows):
            if AI_STOP.is_set():
                break
            with AI_LOCK:
                AI_STATE["current"] = row.get("azienda", "")
            data = dict(row["data"])
            data["formula"] = FORMULE[idx % len(FORMULE)]
            try:
                out = generate_personalization(data)
            except QuotaExhausted as e:
                with AI_LOCK:
                    AI_STATE["quota"] = True
                    AI_STATE["error"] = str(e)
                break
            except Exception as e:
                with AI_LOCK:
                    AI_STATE["error"] = str(e)
                break
            cc = db.get(models.CampaignCompany, row["cc_id"])
            if cc:
                cc.contesto = (out.get("contesto") or "").strip()
                cc.gancio = (out.get("gancio") or "").strip()
                cc.tipo_gancio = (out.get("tipo_gancio") or "").strip()
                if out.get("flag") in ("OK", "Correzione", "Verifica", "Sensibile"):
                    cc.flag = out["flag"]
                cc.paragrafo_apertura = build_apertura(cc.contesto or "", cc.gancio or "")
                con = db.get(models.Contact, cc.contact_id) if cc.contact_id else None
                em = (con.email if con else "") or ""
                cc.draft_status = "Pronta" if (cc.contesto and cc.gancio and em) else "Bozza"
                db.commit()
                with AI_LOCK:
                    AI_STATE["done"] += 1
                    AI_STATE["generated"] += 1
    finally:
        db.close()
        with AI_LOCK:
            AI_STATE["running"] = False
