# -*- coding: utf-8 -*-
"""Scansione delle risposte in arrivo (IMAP, sola lettura su INBOX).

Doppio aggancio, dal piu' preciso al piu' generale:

1) THREAD — `In-Reply-To` / `References` del messaggio ricevuto confrontati con
   il `Message-ID` che abbiamo generato all'invio (vedi mailer.build_message).
   Aggancio esatto, vale per gli invii fatti da quando esiste questa funzione.

2) MITTENTE — indirizzo `From` confrontato con i contatti gia' scritti. Copre
   anche lo storico, ma sbaglia se la persona risponde da un indirizzo diverso
   da quello a cui abbiamo scritto.

Cosa viene salvato: data, mittente e oggetto. NON il testo della risposta, per
non conservare contenuto di corrispondenza a database.

Effetti: il contatto che ha risposto esce dal recall; se l'oggetto e' una
richiesta di rimozione, viene messo in opt-out (come promette l'informativa).
"""
import email
import imaplib
import re
import threading
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime

from app import config
from app.db import SessionLocal

STATE = {"running": False, "total": 0, "done": 0, "trovate": 0, "opt_out": 0,
         "error": "", "current": "", "finished": False, "esito": ""}

COMMIT_OGNI = 20   # salva a blocchi: una scansione interrotta non perde il lavoro
LOCK = threading.Lock()

# Oggetto con cui l'informativa chiede la rimozione (email_builder.PRIVACY).
RIMOZIONE = re.compile(r"richiesta\s+rimozione\s+dalla\s+lista", re.I)


def _decodifica(valore):
    """Intestazione MIME -> testo leggibile, senza mai sollevare."""
    if not valore:
        return ""
    try:
        return str(make_header(decode_header(valore))).strip()
    except Exception:
        return str(valore).strip()


def _indirizzo(valore):
    """Estrae l'indirizzo da un campo From, in minuscolo."""
    if not valore:
        return ""
    m = re.search(r"[\w.!#$%&'*+/=?^`{|}~-]+@[\w-]+(?:\.[\w-]+)+", valore)
    return m.group(0).lower() if m else ""


def _msgids(valore):
    """Tutti i Message-ID contenuti in In-Reply-To / References."""
    return re.findall(r"<[^<>@\s]+@[^<>\s]+>", valore or "")


def _quando(msg):
    try:
        d = parsedate_to_datetime(msg.get("Date"))
        if d and d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except Exception:
        return None


def _imap_inbox():
    """Connessione IMAP alla posta in arrivo del canale Gmail configurato."""
    host, port = config.IMAP_SERVER, config.IMAP_PORT
    user, pwd = config.SENDER_EMAIL, config.SMTP_PASSWORD
    if not (host and user and pwd):
        raise RuntimeError("IMAP non configurato (IMAP_SERVER / SENDER_EMAIL / SMTP_PASSWORD)")
    imap = imaplib.IMAP4_SSL(host, port)
    imap.login(user, pwd)
    typ, _ = imap.select("INBOX", readonly=True)
    if typ != "OK":
        raise RuntimeError("INBOX non accessibile")
    return imap


def _nostri_indirizzi():
    return {(config.SENDER_EMAIL or "").lower(), (config.REPLY_TO or "").lower(),
            (config.ARUBA_EMAIL or "").lower()} - {""}


def scan_replies(giorni=None):
    """Scansiona INBOX e segna le risposte. Ritorna un messaggio di esito.

    La guardia "gia' in corso" sta in avvia_scan(), che e' il punto d'ingresso
    normale: qui si entra gia' con STATE["running"] impostato.
    """
    from app import models
    giorni = int(giorni or config.REPLY_SCAN_DAYS)
    with LOCK:
        STATE.update(running=True, error="", finished=False)
    imap = None
    db = SessionLocal()
    try:
        imap = _imap_inbox()
        da = (datetime.now(timezone.utc) - timedelta(days=giorni)).strftime("%d-%b-%Y")
        typ, dati = imap.search(None, "SINCE", da)
        if typ != "OK":
            raise RuntimeError("ricerca IMAP fallita")
        numeri = (dati[0] or b"").split()
        with LOCK:
            STATE["total"] = len(numeri)
        nostri = _nostri_indirizzi()

        for i, num in enumerate(numeri, 1):
            _passo(db, imap, num, nostri, models)
            if i % COMMIT_OGNI == 0:
                db.commit()  # a blocchi: se si interrompe, quanto trovato resta
            with LOCK:
                STATE["done"] += 1
        db.commit()
        with LOCK:
            esito = (f"Scansione completata: {STATE['trovate']} risposte, "
                     f"{STATE['opt_out']} richieste di rimozione "
                     f"(su {STATE['total']} messaggi degli ultimi {giorni} giorni)")
            STATE["esito"] = esito
        return esito
    except Exception as e:
        db.rollback()
        with LOCK:
            STATE["error"] = str(e)
            STATE["esito"] = f"Errore scansione: {e}"
        return f"Errore scansione: {e}"
    finally:
        db.close()
        try:
            if imap:
                imap.close()
                imap.logout()
        except Exception:
            pass
        with LOCK:
            STATE["running"] = False
            STATE["finished"] = True


def avvia_scan(giorni=None):
    """Lancia la scansione in un thread: la richiesta HTTP torna subito.

    Serve su Cloud Run, dove una richiesta che supera il timeout verrebbe
    troncata. L'avanzamento si legge da /risposte/status.
    """
    with LOCK:
        if STATE["running"]:
            return False
        STATE.update(running=True, total=0, done=0, trovate=0, opt_out=0,
                     error="", current="", finished=False, esito="")
    threading.Thread(target=scan_replies, args=(giorni,), daemon=True).start()
    return True


def _passo(db, imap, num, nostri, models):
    """Elabora un singolo messaggio. True se riconosciuto come risposta."""
    try:
        typ, dati = imap.fetch(num, "(BODY.PEEK[HEADER])")
        if typ != "OK" or not dati or not isinstance(dati[0], tuple):
            return False
        msg = email.message_from_bytes(dati[0][1])
    except Exception:
        return False

    mittente = _indirizzo(msg.get("From"))
    if not mittente or mittente in nostri:
        return False  # scarta la posta che ci siamo mandati da soli (es. il TEST)

    msgid = (msg.get("Message-ID") or "").strip()
    chiave = f"reply:{msgid or f'{mittente}:{num.decode()}'}"
    if db.query(models.OutreachEvent).filter_by(idempotency_key=chiave).first():
        return False  # gia' elaborato in una scansione precedente

    oggetto = _decodifica(msg.get("Subject"))
    quando = _quando(msg) or datetime.now(timezone.utc)

    # 1) aggancio per thread: esatto
    con, aggancio = None, ""
    riferimenti = _msgids(msg.get("In-Reply-To")) + _msgids(msg.get("References"))
    if riferimenti:
        inviata = (db.query(models.OutreachMessage)
                   .filter(models.OutreachMessage.message_id_header.in_(riferimenti))
                   .first())
        if inviata and inviata.contact_id:
            con = db.get(models.Contact, inviata.contact_id)
            if con is not None:
                aggancio = "thread"

    # 2) aggancio per mittente: copre lo storico
    if con is None:
        con = (db.query(models.Contact)
               .filter(models.Contact.email_normalized == mittente).first())
        if con is not None:
            aggancio = "mittente"
    if con is None:
        return False  # non e' una risposta a noi: ignorata

    nuova = con.risposto_at is None or (con.risposto_at and quando > con.risposto_at)
    if nuova:
        con.risposto_at = quando
        con.risposta_oggetto = oggetto[:300] or None
        con.risposta_da = mittente

    rimozione = bool(RIMOZIONE.search(oggetto))
    if rimozione and not con.opt_out:
        con.opt_out = True
        con.opt_out_at = quando
        with LOCK:
            STATE["opt_out"] += 1

    db.add(models.OutreachEvent(
        idempotency_key=chiave,
        event_type="opt_out_request" if rimozione else "replied",
        contact_id=con.contact_id,
        payload={"da": mittente, "oggetto": oggetto[:300], "aggancio": aggancio},
        occurred_at=quando))
    with LOCK:
        STATE["trovate"] += 1
        STATE["current"] = f"{mittente} — {oggetto[:60]}"
    return True


def ultime_risposte(db, limite=60):
    """Chi ha risposto, dal piu' recente: azienda, indirizzo, oggetto, campagna.

    Un contatto puo' comparire in piu' campagne: si riporta la riga di campagna
    piu' recente, che e' quella da cui si arriva alla sua anteprima.
    """
    from app import models
    contatti = (db.query(models.Contact)
                .filter(models.Contact.risposto_at.isnot(None))
                .order_by(models.Contact.risposto_at.desc())
                .limit(limite).all())
    out = []
    for con in contatti:
        comp = db.get(models.Company, con.company_id) if con.company_id else None
        cc = (db.query(models.CampaignCompany)
              .filter_by(contact_id=con.contact_id)
              .order_by(models.CampaignCompany.created_at.desc()).first())
        camp = db.get(models.Campaign, cc.campaign_id) if cc else None
        nome = " ".join(x for x in ((con.first_name or ""), (con.last_name or "")) if x).strip()
        out.append({
            "nome": nome or (con.email or ""),
            "azienda": comp.legal_name if comp else "",
            "email": con.email or "",
            "risposta_da": con.risposta_da or "",
            "quando": con.risposto_at,
            "oggetto": con.risposta_oggetto or "",
            "opt_out": bool(con.opt_out),
            "cc_id": str(cc.campaign_company_id) if cc else "",
            "campagna": camp.name if camp else "",
        })
    return out


def conta_risposte(db, campaign_id=None):
    """Quante risposte risultano, in totale o in una campagna."""
    from app import models
    q = (db.query(models.Contact)
         .filter(models.Contact.risposto_at.isnot(None)))
    if campaign_id is not None:
        q = (q.join(models.CampaignCompany,
                    models.CampaignCompany.contact_id == models.Contact.contact_id)
             .filter(models.CampaignCompany.campaign_id == campaign_id))
    return q.count()
