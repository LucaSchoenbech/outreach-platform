# -*- coding: utf-8 -*-
"""Generazione AI della personalizzazione (contesto + gancio).

Provider principale: DeepSeek (API OpenAI-compatibile), modello configurabile
(default: deepseek-v4.1-flash). Fallback: Gemini.
Rileva l'esaurimento di quota/credito e lo segnala.
"""
import json
import threading

import requests

from app import config

AI_STATE = {"running": False, "total": 0, "done": 0, "current": "", "error": "",
            "quota": False, "generated": 0, "model": config.DEEPSEEK_MODEL,
            "provider": "DeepSeek"}
AI_LOCK = threading.Lock()
AI_STOP = threading.Event()


class QuotaExhausted(Exception):
    """Quota/credito API esaurito."""


class AIError(Exception):
    pass


PROMPT = """Sei Luca Roberto Schoenbech, Temporary Recruiter e Talent Search Advisor
italiano: supporto alla ricerca e valutazione di manager e specialisti senior. Ricevi i
DATI DI RICERCA su un'azienda target e devi personalizzare l'apertura di una email di
presentazione.

FORMULA FISSA (non modificarla, completa solo i due segnaposto):
"sono Luca Roberto Schoenbech, Temporary Recruiter e Talent Search Advisor. Mi occupo
di supporto alla ricerca e valutazione di manager e specialisti senior, con particolare
attenzione ai profili <PROFILI> (anche) nel settore <SETTORE>."

Esempio corretto:
"...con particolare attenzione ai profili tecnici, agronomici e di sviluppo prodotto nel
settore della nutrizione biologica e dei biostimolanti per l'agricoltura."
  -> "gancio": "tecnici, agronomici e di sviluppo prodotto"
  -> "contesto": "della nutrizione biologica e dei biostimolanti per l'agricoltura"

Rispondi SOLO con un oggetto JSON con questi campi:
- "contesto" = <SETTORE>: completa "nel settore ...". Inizia con "del ", "della ",
  "dei ", "delle ", "degli " o "dell'". Sintetico: descrive il settore e l'attività
  concreta dell'azienda (prodotti, tecnologie, mercato servito), senza elencare troppe
  cose. Massimo 12 parole. Niente punto finale.
- "gancio" = <PROFILI>: completa "ai profili ...". Elenco di 2-3 famiglie di profili
  concrete ma CONCISE (es. "di produzione, process engineering e manutenzione su impianti
  a ciclo continuo", "di validazione GMP, technology transfer e qualità", "di
  refrigerazione, progettazione meccanica ed elettronica"). Massimo 12 parole in totale.
  Solo qualifiche e specializzazioni: NON ripetere la parola "profili", niente verbi,
  niente frasi relative ("dove", "in cui"), niente giudizi di scarsità o di mercato,
  niente punto finale.
- "tipo_gancio": "Neutro" se i profili sono generici, altrimenti "Visibilità".
- "flag": uno tra "OK", "Correzione", "Verifica", "Sensibile".

QUALITÀ (profili concreti e distintivi, non generici):
- Nei dati di ricerca trovi attività, competenze e spesso una frase "Il gancio è ...":
  estrai gli elementi distintivi (tecnologie, processi, prodotti, normative, mercati) e
  trasformali in profili e competenze concrete.
- VIETATO limitarsi a elenchi generici ("tecnici e manageriali", "produzione e qualità")
  quando i dati offrono elementi specifici: usali.
- Se i dati suggeriscono un gancio, i profili devono riprenderne la sostanza tecnica
  (es. "impianti a ciclo continuo", "refrigeranti naturali", "GMP", "stampi", "customs").
- CONCISIONE: la frase deve restare scorrevole. 2-3 voci essenziali, non elenchi lunghi
  o dettagli sovrabbondanti.
- NIENTE RIPETIZIONI tra settore e profili, nemmeno con parole della stessa famiglia
  (es. "radiofarmaci"/"radiofarmaceutico", "farmaci"/"farmaceutico"): il termine
  distintivo va di norma nel settore; nei profili usa concetti diversi.
- Esempio da NON produrre (ripetitivo e prolisso):
    settore: "dei radiofarmaci e delle terapie con radioligandi in oncologia"
    profili: "QA/QC e microbiologia per produzioni sterili, radiochemici e ingegneri di
    impianto radiofarmaceutico"
  Versione corretta per gli stessi dati:
    settore: "dei radiofarmaci e dei radioligandi in oncologia"
    profili: "di QA/QC e microbiologia per produzioni sterili, radiochemica e ingegneria
    di impianto"

REGOLE TASSATIVE:
- La formula fissa non si cambia: produci SOLO i due segnaposto.
- Coerenza: i profili devono essere quelli che un'azienda di quel settore cerca
  davvero (tecnici, produzione, qualità, R&D, regulatory, commerciali, operations...).
- Il settore non deve ripetere parole dei profili e viceversa (vale anche per parole
  della stessa famiglia).
- NON inventare: clienti, incarichi svolti, conoscenza diretta dell'azienda, dati non
  verificati. Niente numeri, fatturati, acquisizioni, nomi di clienti.
- Italiano naturale e sobrio, tono professionale senior: niente toni commerciali,
  superlativi o formule generate automaticamente.

GUARDRAIL:
- Situazione delicata (ammortizzatori sociali, crisi, discontinuità, fermo produzione,
  ricapitalizzazione) -> profili generici ("tecnici e manageriali"), "tipo_gancio":
  "Neutro", "flag": "Sensibile".
- Timing "BASSO" o con "MONITORARE" -> profili generici, "tipo_gancio": "Neutro".
- Timing con "VERIFICARE" -> "flag": "Verifica".
- Alert che corregge il settore (errato/troppo stretto/incompleto) -> "flag": "Correzione".
- Se non ci sono né dati di ricerca né "versione_attuale" -> "gancio": "" e
  "tipo_gancio": "Neutro".

VERSIONE ATTUALE (campo "versione_attuale" nei DATI, quando i dati di ricerca sono
assenti o scarsi):
- Contiene il settore ("settore") e i profili ("profili") già presenti in bozza.
- Mantieni la sostanza: stesso settore e profili coerenti con quelli attuali.
- Proponi SEMPRE una versione leggermente diversa: riordina o riformula i profili e,
  quando pertinente, integra 1-2 famiglie di profili in più o una breve precisazione
  sulle competenze. Non ricopiare identica la versione attuale.
- Obiettivo: una versione leggermente diversa della stessa apertura, senza stravolgere
  settore e profili.

DATI DI RICERCA (JSON):
"""


def _split(v):
    return [x.strip() for x in (v or "").split(",") if x.strip()]


def _call_deepseek(text, system=None):
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
                      "messages": [{"role": "system", "content": system or PROMPT},
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


def build_prompt(esempi=""):
    """Prompt di sistema, con le correzioni dell'operatore se presenti.

    Il blocco esempi entra subito prima dei dati di ricerca, cosi' resta
    l'ultima istruzione letta prima dell'input.
    """
    if not esempi:
        return PROMPT
    return PROMPT.replace("DATI DI RICERCA (JSON):",
                          esempi.strip() + "\n\nDATI DI RICERCA (JSON):")


def generate_personalization(data, esempi=""):
    """Prova DeepSeek, poi Gemini. Ritorna dict {contesto, gancio, tipo_gancio, flag}.

    `esempi` e' il blocco con le correzioni manuali precedenti (vedi
    app/learning.py).
    """
    prompt = build_prompt(esempi)
    dati = json.dumps(data, ensure_ascii=False)
    errors = []
    quota_msgs = []
    if config.DEEPSEEK_API_KEY:
        try:
            # DeepSeek: istruzioni nel system, solo i dati nel messaggio utente.
            return _call_deepseek(dati, prompt)
        except QuotaExhausted as e:
            quota_msgs.append(str(e))
        except Exception as e:
            errors.append(f"DeepSeek: {e}")
    if config.GEMINI_API_KEY:
        try:
            # Gemini: un unico turno, istruzioni e dati insieme.
            return _call_gemini(prompt + dati)
        except QuotaExhausted as e:
            quota_msgs.append(str(e))
        except Exception as e:
            errors.append(f"Gemini: {e}")
    if quota_msgs and not errors:
        raise QuotaExhausted(" ".join(quota_msgs))
    raise AIError(" | ".join(errors + quota_msgs) or "nessun provider AI configurato")


def generate_one(cc_id):
    """Rigenera la personalizzazione di un singolo contatto. Ritorna un messaggio."""
    from app import learning, models
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
        if (cc.contesto or "").strip() or (cc.gancio or "").strip():
            data["versione_attuale"] = {"settore": (cc.contesto or "").strip(),
                                        "profili": (cc.gancio or "").strip()}
        if not any([data["attivita"], data["competenze"], data["segnale"], data["alert"]]) \
                and "versione_attuale" not in data:
            return "Nessun dato di ricerca per questo contatto"
        # Solo le correzioni registrate prima dell'ingresso in campagna di questa
        # riga: il lavoro in corso non cambia regole sotto i piedi.
        esempi = learning.blocco_prompt(
            learning.esempi_validi(learning.carica_correzioni(db), cc.created_at))
        out = generate_personalization(data, esempi)
        cc.contesto = (out.get("contesto") or "").strip()
        cc.gancio = (out.get("gancio") or "").strip()
        cc.contesto_ai, cc.gancio_ai = cc.contesto, cc.gancio
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
    from app import learning, models
    from app.db import SessionLocal
    from app.email_builder import build_apertura
    with AI_LOCK:
        AI_STATE.update(running=True, total=len(rows), done=0, current="",
                        error="", quota=False, generated=0)
    db = SessionLocal()
    try:
        correzioni = learning.carica_correzioni(db)
        for idx, row in enumerate(rows):
            if AI_STOP.is_set():
                break
            with AI_LOCK:
                AI_STATE["current"] = row.get("azienda", "")
            data = dict(row["data"])
            esempi = learning.blocco_prompt(
                learning.esempi_validi(correzioni, row.get("cutoff")))
            try:
                out = generate_personalization(data, esempi)
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
                cc.contesto_ai, cc.gancio_ai = cc.contesto, cc.gancio
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
