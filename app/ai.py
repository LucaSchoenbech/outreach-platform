# -*- coding: utf-8 -*-
"""Generazione AI della personalizzazione (contesto + gancio).

Provider principale: DeepSeek (API OpenAI-compatibile), modello configurabile
(default: deepseek-v4.1-flash). Fallback: Gemini.
Rileva l'esaurimento di quota/credito e lo segnala.
"""
import json
import re
import threading

import requests

from app import config

AI_STATE = {"running": False, "total": 0, "done": 0, "current": "", "error": "",
            "quota": False, "generated": 0, "sotto_soglia": 0,
            "model": config.DEEPSEEK_MODEL,
            "provider": "DeepSeek"}
AI_LOCK = threading.Lock()
AI_STOP = threading.Event()


class QuotaExhausted(Exception):
    """Quota/credito API esaurito."""


class AIError(Exception):
    pass


PROMPT = """Sei Luca Roberto Schoenbech, consulente che legge i mercati professionali
(attraversando filiere diverse di proposito) e fa mappature di mercato e competenze.
Ricevi i DATI DI RICERCA su un'azienda target e devi produrre i tre valori che
personalizzano una email di primo contatto.

FORMULA FISSA (non modificarla, produci SOLO i tre valori):
oggetto: "Mappatura di mercato e competenze — <TECNOLOGIA>"
apertura: "sono Luca Roberto Schoenbech. Lavoro sui mercati professionali dell'industria:
<FILIERE>. Dialogo con <FUNZIONI>."

Esempio corretto (azienda di imballaggi in plastica):
  -> "tecnologia": "estrusione e stampaggio"
  -> "contesto": "imballaggi in plastica e gomma, chimica, medicale"
  -> "gancio": "responsabili di produzione, ingegneri di processo, tecnici della qualità"

Rispondi SOLO con un oggetto JSON con questi campi:
- "tecnologia": 2-5 parole, la tecnologia o il processo concreto dell'azienda, come compare
  nei dati (es. "estrusione e stampaggio", "formatura e converting", "produzione sterile").
  Niente punto finale, niente inglese se esiste il termine italiano.
- "contesto" = <FILIERE>: elenco di 2-3 filiere separate da virgola, SENZA articoli
  (es. "imballaggi in plastica e gomma, chimica, medicale"). Scegli SOLO tra questi gruppi:
  Life Sciences, Healthcare e Medical Devices; chimica, cosmetica e consumer health;
  industria, automazione e impiantistica; packaging e servizi B2B. MAI settori fuori da
  questo elenco. Massimo 12 parole.
- "gancio" = <FUNZIONI>: completa "Dialogo con ...". Elenco di 2-4 figure professionali
  concrete e coerenti con quell'azienda (es. "responsabili di produzione, ingegneri di
  processo, tecnici della qualità", "specialisti di validazione GMP e technology transfer",
  "progettisti di stampi e automazione"). Massimo 14 parole. Inizia con un nome/ruolo,
  NON con "di". Niente verbi, non ripetere "profili", niente frasi relative ("dove",
  "in cui"), niente giudizi di scarsità o di mercato, niente punto finale.
- "tipo_gancio": "Neutro" se le funzioni sono generiche, altrimenti "Visibilità".
- "flag": uno tra "OK", "Correzione", "Verifica", "Sensibile".

QUALITÀ (concreto e distintivo, non generico):
- Nei dati trovi attività, competenze e spesso una frase "Il gancio è ...": estrai gli
  elementi distintivi (tecnologie, processi, prodotti, normative) e usali.
- VIETATO limitarsi a elenchi generici ("tecnici e manageriali") quando i dati offrono
  elementi specifici.
- CONCISIONE: 2-3 voci essenziali, frasi scorrevoli.
- NESSUNA RIPETIZIONE tra tecnologia, filiere e funzioni, nemmeno con parole della stessa
  famiglia (es. "radiofarmaci"/"radiofarmaceutico", "estrusione"/"estrusori").

REGOLE TASSATIVE:
- Formula fissa: produci SOLO i tre valori.
- NON inventare: clienti, incarichi, mandati chiusi, numeri, tempi, referenze, settori
  fuori dall'elenco. Niente prezzi, costi o tariffe.
- Non usare le parole "recruiter", "head hunting", "ricerca e selezione" riferite al
  lavoro di Schoenbech.
- Italiano naturale e sobrio, professionale, senza superlativi né toni commerciali.

GUARDRAIL:
- Situazione delicata (ammortizzatori sociali, crisi, discontinuità, fermo produzione,
  ricapitalizzazione) -> funzioni generiche ("tecnici e manageriali"), "tipo_gancio":
  "Neutro", "flag": "Sensibile".
- Timing con "VERIFICARE" -> "flag": "Verifica". Il timing NON abbassa mai il livello
  di dettaglio: un contatto da coltivare merita la stessa cura degli altri.
- Alert che corregge il settore (errato/troppo stretto/incompleto) -> "flag": "Correzione".
- Se non ci sono né dati di ricerca né "versione_attuale" -> tutti i campi vuoti.

VERSIONE ATTUALE (campo "versione_attuale" nei DATI, quando i dati di ricerca sono
assenti o scarsi):
- Contiene tecnologia, filiere ("settore") e funzioni ("profili") già presenti in bozza.
- Mantieni la sostanza e proponi una versione leggermente diversa; puoi integrare 1-2
  funzioni in più o una precisazione sulle competenze. Non ricopiare identica.

DATI DI RICERCA (JSON):
"""


def _split(v):
    return [x.strip() for x in (v or "").split(",") if x.strip()]


# ---------------------------------------------------------------------------
# Soglia di qualita'
# ---------------------------------------------------------------------------
# Formule che non dicono nulla di quell'azienda: se l'uscita si riduce a
# queste, l'email vale meno di una non spedita.
_GENERICHE = re.compile(
    r"\b(tecnic\w+ e manageriali|figure tecniche|profili tecnici|personale tecnico|"
    r"ruoli tecnici|tecnici e manager|figure professionali|risorse qualificate)\b", re.I)

# Parola comune ai tre campi = ripetizione. Si ignorano le parole di servizio.
_VUOTE = {"e", "di", "del", "della", "dei", "delle", "in", "su", "per", "con", "a",
          "da", "il", "lo", "la", "i", "gli", "le", "un", "una", "dell", "all"}


def _parole(testo):
    return {p for p in re.findall(r"[a-zà-ù]{4,}", (testo or "").lower()) if p not in _VUOTE}


def valuta_qualita(out):
    """Misura l'uscita dell'AI. Ritorna (va_bene, elenco_problemi).

    Una situazione delicata produce di proposito funzioni generiche: li' il
    generico e' la risposta giusta, non un difetto, e non viene segnalato.
    """
    tec = (out.get("tecnologia") or "").strip()
    filiere = (out.get("contesto") or "").strip()
    funzioni = (out.get("gancio") or "").strip()
    if (out.get("flag") or "").strip() == "Sensibile":
        return True, []

    problemi = []
    if not tec:
        problemi.append("tecnologia assente")
    elif not 1 <= len(tec.split()) <= 6:
        problemi.append(f"tecnologia di {len(tec.split())} parole")
    if not filiere:
        problemi.append("filiere assenti")
    elif len(_split(filiere)) < 2:
        problemi.append("una sola filiera")
    if not funzioni:
        problemi.append("funzioni assenti")
    else:
        voci = len(_split(funzioni))
        if voci < 2:
            problemi.append("una sola funzione")
        if _GENERICHE.search(funzioni):
            problemi.append("funzioni generiche")
    comuni = _parole(tec) & _parole(filiere) | _parole(tec) & _parole(funzioni) \
        | _parole(filiere) & _parole(funzioni)
    if comuni:
        problemi.append("ripetizioni fra i campi: " + ", ".join(sorted(comuni)[:3]))
    return (not problemi), problemi


_RICHIAMO = (
    "\n\nATTENZIONE: la risposta precedente non raggiungeva lo standard richiesto "
    "({problemi}). Riscrivi usando gli elementi concreti presenti nei dati "
    "(tecnologie, processi, prodotti, normative). Niente formule generiche.")


def genera_con_soglia(data, esempi=""):
    """Genera e, se l'uscita e' debole, ritenta una volta sola.

    Ritorna (uscita, problemi_residui). Con problemi residui la riga non va
    promossa a Pronta: resta in Bozza, marcata, cosi' si vede e si rigenera
    in blocco invece di scoprirla leggendo l'anteprima.
    """
    out = generate_personalization(data, esempi)
    ok, problemi = valuta_qualita(out)
    if ok:
        return out, []
    secondo = generate_personalization(data, esempi + _RICHIAMO.format(
        problemi="; ".join(problemi)))
    ok2, problemi2 = valuta_qualita(secondo)
    if ok2:
        return secondo, []
    # Si tiene il tentativo con meno difetti.
    return (secondo, problemi2) if len(problemi2) <= len(problemi) else (out, problemi)


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
        if (cc.contesto or "").strip() or (cc.gancio or "").strip() or (cc.tecnologia or "").strip():
            data["versione_attuale"] = {"settore": (cc.contesto or "").strip(),
                                        "profili": (cc.gancio or "").strip(),
                                        "tecnologia": (cc.tecnologia or "").strip()}
        if not any([data["attivita"], data["competenze"], data["segnale"], data["alert"]]) \
                and "versione_attuale" not in data:
            return "Nessun dato di ricerca per questo contatto"
        # Solo le correzioni registrate prima dell'ingresso in campagna di questa
        # riga: il lavoro in corso non cambia regole sotto i piedi.
        esempi = learning.blocco_prompt(
            learning.esempi_validi(learning.carica_correzioni(db), cc.created_at))
        out, problemi = genera_con_soglia(data, esempi)
        nuova_tec = (out.get("tecnologia") or "").strip()
        if nuova_tec:
            cc.tecnologia = nuova_tec
        cc.contesto = (out.get("contesto") or "").strip()
        cc.gancio = (out.get("gancio") or "").strip()
        cc.contesto_ai, cc.gancio_ai = cc.contesto, cc.gancio
        cc.tipo_gancio = (out.get("tipo_gancio") or "").strip()
        if out.get("flag") in ("OK", "Correzione", "Verifica", "Sensibile"):
            cc.flag = out["flag"]
        cc.paragrafo_apertura = build_apertura(cc.contesto or "", cc.gancio or "")
        cc.qualita_note = "; ".join(problemi) or None
        cc.ai_modello = AI_STATE.get("model")
        em = (con.email if con else "") or ""
        # Sotto soglia resta Bozza: non puo' partire per sbaglio.
        cc.draft_status = ("Pronta" if (cc.contesto and cc.gancio and em and not problemi)
                           else "Bozza")
        db.commit()
        return ("Personalizzazione aggiornata" if not problemi
                else "Aggiornata ma sotto standard: " + "; ".join(problemi))
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
                        error="", quota=False, generated=0, sotto_soglia=0)
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
                out, problemi = genera_con_soglia(data, esempi)
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
                nuova_tec = (out.get("tecnologia") or "").strip()
                if nuova_tec:
                    cc.tecnologia = nuova_tec
                cc.contesto = (out.get("contesto") or "").strip()
                cc.gancio = (out.get("gancio") or "").strip()
                cc.contesto_ai, cc.gancio_ai = cc.contesto, cc.gancio
                cc.tipo_gancio = (out.get("tipo_gancio") or "").strip()
                if out.get("flag") in ("OK", "Correzione", "Verifica", "Sensibile"):
                    cc.flag = out["flag"]
                cc.paragrafo_apertura = build_apertura(cc.contesto or "", cc.gancio or "")
                cc.qualita_note = "; ".join(problemi) or None
                cc.ai_modello = AI_STATE.get("model")
                con = db.get(models.Contact, cc.contact_id) if cc.contact_id else None
                em = (con.email if con else "") or ""
                # Sotto soglia resta Bozza: non puo' partire per sbaglio.
                cc.draft_status = ("Pronta" if (cc.contesto and cc.gancio and em
                                                and not problemi) else "Bozza")
                db.commit()
                with AI_LOCK:
                    AI_STATE["done"] += 1
                    AI_STATE["generated"] += 1
                    if problemi:
                        AI_STATE["sotto_soglia"] = AI_STATE.get("sotto_soglia", 0) + 1
    finally:
        db.close()
        with AI_LOCK:
            AI_STATE["running"] = False
