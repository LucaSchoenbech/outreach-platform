# -*- coding: utf-8 -*-
"""Costruzione email (testo + HTML) per invio massivo e recall."""
import html
import os
import re
from datetime import datetime, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None

LINK = "https://schoenbech.com/attivita-consulenza-overview.pdf"

# Esempio reale di mappatura (ricerca Responsabile Pricing, dati anonimizzati).
# Finché è vuoto, mailer.run_send/do_test bloccano l'invio delle email che lo citano.
# Link aperto (riutilizzabile, sola lettura) al progetto /progetti/6 di Talent Mapping.
LINK_MAPPATURA = os.getenv(
    "LINK_MAPPATURA",
    "https://businessintelligence.schoenbech.com/accesso/1u3i1QKs5T7ivJph_uAHbqBMIkuoCa-m",
).strip()

_STATIC_LOGO = Path(__file__).resolve().parent.parent / "static" / "logo_email.png"
_WIN_LOGO = Path(r"C:\Users\Luca R\Downloads\sviluppo schoenbech\logo_schoenbech.png")
LOGO = _STATIC_LOGO if _STATIC_LOGO.exists() else _WIN_LOGO

SUBJECT = "Recruitment As a Service : Schoenbech | Talent Advisory"

APERTURA_BASE = ("mi permetto di presentarmi: sono Luca Roberto Schoenbech, Talent Search Advisor. "
                 "Mi occupo di ricerca e valutazione di manager e specialisti senior, "
                 "con particolare attenzione al mondo ")

CORPO = """Ogni incarico, oltre alla rosa dei candidati, produce una mappatura analitica del mercato, costruita sui colloqui diretti con i professionisti: chi ricopre oggi ruoli comparabili e in quali aziende, come quelle aziende organizzano il ruolo, quali sono i livelli retributivi di mercato e le aspettative, quanti sono disponibili a valutare un cambiamento e per quali motivi gli altri non lo sono. L'azienda la consulta in un'area riservata, aggiornata durante tutta la ricerca, e la usa per decidere sui dati: non solo quale candidato scegliere, ma anche se l'offerta è competitiva o se il profilo va ricalibrato.

Può vedere qui un esempio reale, relativo alla ricerca di un Responsabile Pricing, con i dati resi anonimi a tutela delle persone coinvolte e del cliente: {LINK_MAPPATURA}. Il link si apre direttamente, senza registrazione.

Seguo personalmente ogni fase, **con un modello snello che consente tempi rapidi e costi più contenuti** rispetto all'Executive e Professional Search tradizionale, **senza ridurre la profondità del lavoro**.

Se nei prossimi mesi dovesse cercare un responsabile di funzione o uno specialista senior, sarei lieto di commentare con Lei l'esempio in una breve chiamata e capire se posso esserLe utile.

A questo link può trovare una breve presentazione della mia attività, mentre in calce trova i riferimenti al sito web per ulteriori dettagli: {LINK}"""

CLOSING = "Un cordiale saluto,"

FIRMA_NOME = "Luca Roberto Schoenbech"

PRIVACY = """I suoi dati di contatto professionali provengono da banche dati B2B e da fonti pubbliche, trattati per finalità di ricerca e selezione sulla base del legittimo interesse. Informativa completa qui: https://schoenbech.com/privacy . Per non ricevere più comunicazioni, può richiedere la rimozione rispondendo a questa email con oggetto "Richiesta rimozione dalla lista"."""

RECALL_TEXT = """In primis spero di non essere inopportuno.
Le scrivo la presente per sapere se ha avuto modo e tempo di leggere la comunicazione sotto riportata.

In attesa di un Suo cortese riscontro, voglia gradire i miei migliori saluti ed auguri di un buon lavoro.

(Per comodità: {LINK_BREVE})"""

NOMI_MASCHILI = {"andrea", "nicola", "luca", "mattia", "elia", "enea", "tobia", "giona",
                 "gianluca", "pierluca", "gianmaria", "battista", "barnaba", "sasha",
                 "morlai", "simone", "giuseppe", "matteo", "stefano", "giorgio",
                 "claudio", "lorenzo"}

TITOLI = {"dott", "dott.ssa", "dottore", "dottoressa", "dr", "dr.ssa", "ing", "ingegnere",
          "avv", "avvocato", "arch", "architetto", "rag", "ragioniere", "geom", "geometra",
          "prof", "professore", "sig", "signor", "sig.ra", "signora", "sig.na", "signorina",
          "egr", "gent", "perito", "notaio"}

PARTICELLE = {"de", "del", "dello", "della", "dei", "degli", "delle", "di", "da", "dal",
              "dallo", "dalla", "dai", "dagli", "dalle", "la", "lo", "le", "li", "van",
              "von", "der", "den", "ter", "san", "santa", "sant", "mac", "mc", "abu",
              "bin", "ibn", "dos", "do"}


def infer_titolo(nome):
    parti = str(nome).strip().split()
    n = parti[0].lower() if parti else ""
    if n in NOMI_MASCHILI:
        return "Dott."
    if n.endswith("a"):
        return "Dott.ssa"
    return "Dott."


def saluto_orario(dt=None):
    """'buongiorno' prima delle 16:00 (Europe/Rome), poi 'buonasera'.
    Con dt (es. orario di invio reale) restituisce il saluto di quel momento."""
    try:
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            ora = dt.astimezone(ZoneInfo("Europe/Rome")).hour if ZoneInfo else dt.hour
        else:
            ora = datetime.now(ZoneInfo("Europe/Rome")).hour if ZoneInfo else datetime.now().hour
    except Exception:
        ora = (dt or datetime.now()).hour
    return "buongiorno" if ora < 16 else "buonasera"


def pulisci_nome(contatto):
    """Rimuove ruolo e titoli dal contatto: 'Dott.ssa Nome Cognome — Ruolo' -> 'Nome Cognome'."""
    s = str(contatto).strip()
    s = re.split(r"\s+[—–-]\s+|\s*[|,/;:(]\s*", s, maxsplit=1)[0].strip()
    parti = s.split()
    while parti and parti[0].lower().rstrip(".") in TITOLI:
        parti.pop(0)
    return " ".join(parti)


def dividi_nome(contatto):
    """Divide 'Nome [Nomi] Cognome' in (nomi, cognome), gestendo particelle
    (es. 'Andrea De Luca' -> ('Andrea', 'De Luca'); 'Carla Giulia Ravanello'
    -> ('Carla Giulia', 'Ravanello'))."""
    nome_pulito = pulisci_nome(contatto)
    parti = nome_pulito.split()
    if len(parti) < 2:
        return nome_pulito, ""
    inizio = len(parti) - 1
    while inizio > 1 and parti[inizio - 1].lower().rstrip(".'") in PARTICELLE:
        inizio -= 1
    return " ".join(parti[:inizio]), " ".join(parti[inizio:])


def build_saluto(contatto, titolo=""):
    nome_pulito = pulisci_nome(contatto)
    _, cognome = dividi_nome(nome_pulito)
    if not titolo:
        titolo = infer_titolo(nome_pulito)
    return f"Gentile {titolo} {cognome}".strip()


APERTURA_SENZA_CONTESTO = ("mi permetto di presentarmi: sono Luca Roberto Schoenbech, Talent Search "
                           "Advisor. Mi occupo di ricerca e valutazione di manager e specialisti senior")


def build_apertura(contesto, gancio):
    c = str(contesto).strip()
    g = str(gancio).strip()
    base = (APERTURA_BASE + c) if c else APERTURA_SENZA_CONTESTO
    if g:
        return base + ", " + g.rstrip(".") + "."
    return base + "."


def _plain(testo):
    return str(testo).replace("**", "")


def get_email_template():
    """Testo generale (oggetto, corpo, recall) da DB, con default di fabbrica."""
    tpl = {"subject": SUBJECT, "corpo": CORPO, "recall_text": RECALL_TEXT}
    try:
        from app import models
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            row = db.get(models.EmailTemplate, 1)
            if row:
                if row.subject:
                    tpl["subject"] = row.subject
                if row.corpo:
                    tpl["corpo"] = row.corpo
                if row.recall_text:
                    tpl["recall_text"] = row.recall_text
        finally:
            db.close()
    except Exception:
        pass
    return tpl


def link_mancanti(tpl=None):
    """Segnaposto usati nel testo ma senza URL configurato (invio da bloccare)."""
    t = tpl or {}
    testi = " ".join([t.get("corpo") or CORPO, t.get("recall_text") or RECALL_TEXT])
    return ["LINK_MAPPATURA"] if "{LINK_MAPPATURA}" in testi and not LINK_MAPPATURA else []


def _sostituisci_link_plain(testo):
    return (testo.replace("{LINK_MAPPATURA}", LINK_MAPPATURA or "[link esempio di mappatura]")
            .replace("{LINK_BREVE}", LINK).replace("{LINK}", LINK))


def build_email(row, message_no=1, tpl=None):
    t = tpl or {}
    subject = t.get("subject") or SUBJECT
    corpo = _sostituisci_link_plain(_plain(t.get("corpo") or CORPO))
    recall = _sostituisci_link_plain(_plain(t.get("recall_text") or RECALL_TEXT))
    saluto = row.get("saluto", "")
    # Apertura ricalcolata da contesto/gancio: testo semplice identico all'HTML
    # (paragrafo_apertura salvato all'import resta solo come fallback).
    if row.get("contesto") or row.get("gancio"):
        apertura = build_apertura(row.get("contesto", ""), row.get("gancio", ""))
    else:
        apertura = row.get("paragrafo_apertura", "") or build_apertura("", "")
    buongiorno = saluto_orario()
    ricordato = row.get("saluto_originale") or buongiorno
    corpo_orig = f"{apertura}\n\n{corpo}\n\n{CLOSING}\n{FIRMA_NOME}\n\n{PRIVACY}"
    if message_no == 1:
        return subject, f"{saluto}, {buongiorno},\n\n{corpo_orig}"
    body = (f"{saluto}, {buongiorno},\n\n{recall}\n\n"
            f"----- MESSAGGIO ORIGINALE -----\n\n"
            f"{saluto}, {ricordato},\n\n{corpo_orig}")
    return f"RE: {subject}", body


HTML_TOP = """<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:25px 30px;background:#fff;font-family:Georgia,'Times New Roman',serif;color:#1a2332;">
<p style="font-size:16px;line-height:1.65;margin:0 0 20px 10px;">__SALUTO__, __BUONGIORNO__,</p>
<div style="font-size:16px;line-height:1.65;margin-left:10px;max-width:680px;">"""

HTML_SALUTI = """<p style="margin:0 0 20px 0;">Un cordiale saluto,</p>
<p style="margin:0 0 18px 0;">Luca Roberto Schoenbech</p>"""

HTML_CHIUSURA = HTML_SALUTI + "</div>"

HTML_FIRMA = """<table cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;font-family:Georgia,'Times New Roman',serif;color:#1a2332;margin-left:10px;">
<tr>
<td style="padding:0 30px 0 0;text-align:center;vertical-align:middle;border-right:1px solid #1a2332;">
<img src="__LOGO__" width="70" height="70" alt="Schoenbech" style="display:block;margin:0 auto 12px auto;border:0;outline:none;text-decoration:none;" />
<div style="font-family:Georgia,'Times New Roman',serif;font-size:24px;letter-spacing:6px;color:#1a2332;">SCHOENBECH</div>
<div style="height:1px;background-color:#b08d57;width:50px;margin:10px auto;line-height:1px;font-size:1px;">&nbsp;</div>
<div style="font-family:Arial,Helvetica,sans-serif;font-size:9px;letter-spacing:3px;color:#b08d57;">TALENT&nbsp;&nbsp;SOURCING&nbsp;&nbsp;ADVISORY</div>
</td>
<td style="padding:0 0 0 30px;vertical-align:middle;">
<div style="font-family:Georgia,'Times New Roman',serif;font-size:20px;color:#1a2332;font-weight:bold;padding-bottom:6px;">Luca Roberto Schoenbech</div>
<div style="font-family:Arial,Helvetica,sans-serif;font-size:10px;letter-spacing:3px;color:#b08d57;padding-bottom:14px;">TALENT&nbsp;&nbsp;SOURCING&nbsp;&nbsp;ADVISORY</div>
<table cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#1a2332;">
<tr><td style="color:#b08d57;font-weight:bold;padding:0 12px 4px 0;">M</td><td style="padding:0 0 4px 0;"><a href="tel:+393474037841" style="color:#1a2332;text-decoration:none;">+39 347 4037841</a></td></tr>
<tr><td style="color:#b08d57;font-weight:bold;padding:0 12px 4px 0;">E</td><td style="padding:0 0 4px 0;"><a href="mailto:luca@schoenbech.com" style="color:#1a2332;text-decoration:none;">luca@schoenbech.com</a></td></tr>
<tr><td style="color:#b08d57;font-weight:bold;padding:0 12px 4px 0;">W</td><td style="padding:0 0 4px 0;"><a href="https://schoenbech.com/" style="color:#1a2332;text-decoration:none;">schoenbech.com</a></td></tr>
<tr><td style="color:#b08d57;font-weight:bold;font-style:italic;padding:0 12px 0 0;">in</td><td><a href="https://linkedin.com/company/schoenbech" style="color:#1a2332;text-decoration:none;">linkedin.com/company/schoenbech</a></td></tr>
</table>
</td>
</tr>
</table>"""

HTML_FOOTER = """<table cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;margin-top:18px;max-width:720px;margin-left:10px;">
<tr>
<td style="border-top:1px solid #b08d57;padding-top:10px;font-family:Arial,Helvetica,sans-serif;font-size:10px;color:#888888;line-height:1.4;">
Le informazioni contenute in questa email sono riservate e destinate esclusivamente al destinatario. Se avete ricevuto questa comunicazione per errore, siete pregati di cancellarla e darne comunicazione al mittente.
<br/><br/>
I suoi dati di contatto professionali provengono da banche dati B2B e da fonti pubbliche, trattati per finalit&agrave; di ricerca e selezione sulla base del legittimo interesse. Informativa completa <a href="https://schoenbech.com/privacy" style="color:#b08d57;text-decoration:underline;">qui</a>. Per non ricevere pi&ugrave; comunicazioni, pu&ograve; richiedere la rimozione <a href="mailto:luca@schoenbech.com?subject=Richiesta%20rimozione%20dalla%20lista" style="color:#b08d57;text-decoration:underline;">cliccando qui</a>.
</td>
</tr>
</table></body></html>"""


def _intro_html(contesto, gancio):
    c = str(contesto).strip()
    g = str(gancio).strip()
    base = (APERTURA_BASE + html.escape(c)) if c else APERTURA_SENZA_CONTESTO
    coda = (", " + html.escape(g.rstrip(".")) + ".") if g else "."
    return base + coda


LINK_ANCHOR = (f'<a href="{LINK}" style="color:#b08d57;font-weight:bold;text-decoration:none;">'
               "Presentazione Attivit&agrave; di Consulenza &mdash; Overview</a>")

LINK_ANCHOR_BREVE = (f'<a href="{LINK}" style="color:#b08d57;font-weight:bold;text-decoration:none;">'
                     "la mia presentazione</a>")


def _link_mappatura_html():
    if not LINK_MAPPATURA:
        return "[Presentazione Attivit&agrave; di Mappatura]"
    return (f'<a href="{html.escape(LINK_MAPPATURA, quote=True)}" '
            'style="color:#b08d57;font-weight:bold;text-decoration:none;">Presentazione Attivit&agrave; di Mappatura</a>')


def _corpo_html(corpo):
    paragrafi = [p.strip() for p in str(corpo).replace("\r\n", "\n").split("\n\n") if p.strip()]
    link_html = LINK_ANCHOR
    out = []
    for p in paragrafi:
        p = html.escape(p)
        p = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", p, flags=re.S)
        p = (p.replace("\n", " ").replace("{LINK_MAPPATURA}", _link_mappatura_html())
             .replace("{LINK_BREVE}", LINK_ANCHOR_BREVE).replace("{LINK}", link_html))
        out.append(f'<p style="margin:0 0 22px 0;">{p}</p>')
    return "".join(out)


def build_email_html(row, logo="/logo.png", message_no=1, tpl=None):
    t = tpl or {}
    intro_p = f'<p style="margin:0 0 20px 0;">{_intro_html(row.get("contesto", ""), row.get("gancio", ""))}</p>'
    corpo = _corpo_html(t.get("corpo") or CORPO)
    saluto = str(row.get("saluto", ""))
    if message_no == 2:
        ricordato = row.get("saluto_originale") or saluto_orario()
        recall = (_plain(t.get("recall_text") or RECALL_TEXT)
                  .replace("{LINK_MAPPATURA}", _link_mappatura_html())
                  .replace("{LINK_BREVE}", LINK_ANCHOR_BREVE)
                  .replace("{LINK}", LINK_ANCHOR).replace("\n", "<br>"))
        html = (HTML_TOP
                + f'<p style="margin:0 0 20px 0;">{recall}</p></div>'
                + HTML_FIRMA
                + '<div style="font-size:16px;line-height:1.65;margin-left:10px;max-width:680px;margin-top:18px;">'
                + '<hr style=\'border:0;border-top:1px solid #ccc;margin:16px 0\'>'
                + '<p style="margin:0 0 20px 0;"><b>----- MESSAGGIO ORIGINALE -----</b></p>'
                + f'<p style="margin:0 0 20px 0;">{saluto}, {ricordato},</p>'
                + intro_p + corpo + HTML_SALUTI + "</div>"
                + HTML_FIRMA
                + HTML_FOOTER)
    else:
        html = HTML_TOP + intro_p + corpo + HTML_CHIUSURA + HTML_FIRMA + HTML_FOOTER
    return (html
            .replace("__SALUTO__", saluto)
            .replace("__BUONGIORNO__", saluto_orario())
            .replace("__LOGO__", logo))
