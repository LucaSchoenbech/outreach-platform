# -*- coding: utf-8 -*-
"""Motore di invio: SMTP + copia in Posta inviata (IMAP) + ritmo umano + DB."""
import hashlib
import imaplib
import random
import re
import smtplib
import threading
import time
from datetime import datetime, timedelta, timezone
from email.header import Header
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate

from app import config
from app.db import SessionLocal
from app.email_builder import LOGO, build_email, build_email_html, get_email_template, link_mancanti

STATE = {"running": False, "finished": False, "channel": "Gmail", "message_no": 1,
         "total": 0, "done": 0, "current": "", "log": [], "error": "", "copia": 0,
         "copia_err": "", "started": ""}
STOP = threading.Event()
LOCK = threading.Lock()


def channel_config(channel):
    if channel == "Aruba":
        return {"server": config.ARUBA_SMTP_SERVER, "port": config.ARUBA_SMTP_PORT,
                "user": config.ARUBA_EMAIL, "password": config.ARUBA_PASSWORD}
    return {"server": config.SMTP_SERVER, "port": config.SMTP_PORT,
            "user": config.SENDER_EMAIL, "password": config.SMTP_PASSWORD}


def imap_config(channel):
    if channel == "Aruba":
        return (config.ARUBA_IMAP_SERVER, config.ARUBA_IMAP_PORT,
                config.ARUBA_EMAIL, config.ARUBA_PASSWORD)
    return (config.IMAP_SERVER, config.IMAP_PORT, config.SENDER_EMAIL, config.SMTP_PASSWORD)


def build_message(row, sender, to=None, message_no=1):
    tpl = get_email_template()
    subject, body_text = build_email(row, message_no, tpl)
    html = build_email_html(row, logo="cid:logo_schoenbech", message_no=message_no, tpl=tpl)
    msg = MIMEMultipart("related")
    msg["Subject"] = str(Header(subject, "utf-8"))
    msg["From"] = formataddr((str(Header(config.SENDER_NAME, "utf-8")), sender))
    msg["To"] = to or row["email"]
    msg["Reply-To"] = config.REPLY_TO
    msg["Date"] = formatdate(localtime=True)
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(body_text, "plain", "utf-8"))
    alt.attach(MIMEText(html, "html", "utf-8"))
    msg.attach(alt)
    if LOGO.exists():
        with open(LOGO, "rb") as f:
            img = MIMEImage(f.read())
            img.add_header("Content-ID", "<logo_schoenbech>")
            img.add_header("Content-Disposition", "inline")
            msg.attach(img)
    return msg


def find_sent_folder(imap):
    try:
        typ, data = imap.list()
        if typ == "OK" and data:
            for raw in data:
                s = raw.decode("utf-8", "ignore") if isinstance(raw, (bytes, bytearray)) else str(raw)
                if "\\Sent" in s:
                    m = re.search(r'"[^"]*"\s*$', s)
                    return m.group(0).strip('"') if m else s.split(" ")[-1].strip('"')
    except Exception:
        pass
    for cand in ["[Gmail]/Sent Mail", "[Gmail]/Posta inviata", "INBOX.Sent", "Sent", "Posta Inviata"]:
        try:
            if imap.select(cand)[0] == "OK":
                return cand
        except Exception:
            continue
    return None


def imap_connect(channel):
    host, port, user, pwd = imap_config(channel)
    imap = imaplib.IMAP4_SSL(host, port)
    imap.login(user, pwd)
    return imap, find_sent_folder(imap)


def _persist(row, message_no, channel, subject, ok, err=""):
    """Scrive messaggio + evento + stato nel DB (schema mass)."""
    from app import models
    db = SessionLocal()
    try:
        key = hashlib.sha256(f"{row['cc_id']}|{message_no}|{row['email']}".encode()).hexdigest()
        existing = db.query(models.OutreachMessage).filter_by(dedupe_key=key).first()
        if existing:
            return
        msg = models.OutreachMessage(
            campaign_id=row["campaign_id"], campaign_company_id=row["cc_id"],
            contact_id=row.get("contact_id"), message_no=message_no, channel=channel.lower(),
            to_email=row["email"], subject=subject, status="sent" if ok else "failed",
            dedupe_key=key, sent_at=datetime.now(timezone.utc) if ok else None)
        db.add(msg)
        ev = models.OutreachEvent(
            idempotency_key=f"out:{key}", event_type="sent" if ok else "failed",
            campaign_id=row["campaign_id"], contact_id=row.get("contact_id"),
            payload={"error": err} if err else None)
        db.add(ev)
        cc = db.get(models.CampaignCompany, row["cc_id"])
        if cc and ok:
            cc.status = "contacted"
            if message_no == 1:
                fu = models.FollowUp(campaign_company_id=cc.campaign_company_id,
                                     contact_id=cc.contact_id, sequence_no=2,
                                     due_at=datetime.now(timezone.utc) + timedelta(days=7), status="scheduled")
                db.add(fu)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def run_send(rows, channel, salva_copia=True, message_no=1):
    mancanti = link_mancanti(get_email_template())
    if mancanti:
        with LOCK:
            STATE.update(running=False, finished=True, total=len(rows), done=0,
                         current="Invio bloccato",
                         error=f"Link non configurato: {', '.join(mancanti)}. Nessuna email inviata.")
        return
    ch = channel_config(channel)
    with LOCK:
        STATE.update(running=True, finished=False, channel=channel, message_no=message_no,
                     total=len(rows), done=0, current="Connessione in corso...",
                     log=[], error="", copia=0, copia_err="",
                     started=datetime.now().strftime("%H:%M:%S"))
    smtp = None
    imap = None
    sent_folder = None
    try:
        for idx, row in enumerate(rows, 1):
            if STOP.is_set():
                break
            if smtp is None:
                try:
                    smtp = smtplib.SMTP_SSL(ch["server"], ch["port"], timeout=30)
                    smtp.login(ch["user"], ch["password"])
                except Exception as e:
                    STATE["error"] = f"Connessione {channel} fallita: {e}"
                    break
            try:
                msg = build_message(row, ch["user"], message_no=message_no)
                subject = msg["Subject"]
                smtp.send_message(msg)
                with LOCK:
                    STATE["done"] += 1
                    STATE["current"] = f"✓ {row.get('saluto', '')} ({row.get('azienda', '')})"
                    STATE["log"].append(f"SUCCESS - {row['email']} ({row.get('azienda', '')})")
                _persist(row, message_no, channel, str(subject), True)
                if salva_copia:
                    try:
                        if imap is None or sent_folder is None:
                            imap, sent_folder = imap_connect(channel)
                        if sent_folder:
                            imap.append(sent_folder, "\\Seen",
                                        imaplib.Time2Internaldate(time.time()), msg.as_bytes())
                            with LOCK:
                                STATE["copia"] += 1
                    except Exception as ce:
                        with LOCK:
                            STATE["copia_err"] = str(ce)
                        try:
                            if imap:
                                imap.logout()
                        except Exception:
                            pass
                        imap, sent_folder = None, None
            except Exception as e:
                err = str(e)
                with LOCK:
                    STATE["log"].append(f"ERROR - {row['email']}: {err}")
                _persist(row, message_no, channel, "", False, err)
                try:
                    smtp.quit()
                except Exception:
                    pass
                smtp = None
                if "5.4.5" in err or "Daily user sending limit" in err:
                    STATE["error"] = "Limite giornaliero raggiunto (5.4.5). Invio fermato."
                    break
                continue
            if idx < len(rows):
                d = (random.randint(config.BREAK_MIN, config.BREAK_MAX)
                     if idx % config.PAUSE_EVERY == 0
                     else random.randint(config.DELAY_MIN, config.DELAY_MAX))
                for s in range(d, 0, -1):
                    if STOP.is_set():
                        break
                    STATE["current"] = f"⏳ Prossima email tra {s // 60}m {s % 60:02d}s"
                    time.sleep(1)
    finally:
        try:
            if smtp:
                smtp.quit()
        except Exception:
            pass
        try:
            if imap:
                imap.logout()
        except Exception:
            pass
        with LOCK:
            STATE["running"] = False
            STATE["finished"] = True
            STATE["current"] = "Invio fermato" if STOP.is_set() else "Invio terminato"


def do_test(rows, channel, message_no=1):
    if not rows:
        return "Nessun contatto pronto."
    mancanti = link_mancanti(get_email_template())
    if mancanti:
        return f"Invio bloccato: link non configurato ({', '.join(mancanti)})."
    ch = channel_config(channel)
    try:
        smtp = smtplib.SMTP_SSL(ch["server"], ch["port"], timeout=30)
        smtp.login(ch["user"], ch["password"])
        smtp.send_message(build_message(rows[0], ch["user"], to=ch["user"], message_no=message_no))
        smtp.quit()
        return f"TEST inviato a {ch['user']}."
    except Exception as e:
        return f"Errore TEST: {e}"
