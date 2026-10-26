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

# Pagina pubblica "Esempi di analisi": il destinatario sceglie da se' il caso
# che lo riguarda.
#
# Sostituisce i link di accesso generati dalla piattaforma Business Intelligence
# (businessintelligence.schoenbech.com/accesso/<token>). Quelli scadono per conto
# loro e, una volta scaduti, rispondono 200 con una pagina "Il link non e' valido
# o e' scaduto": un controllo sul codice di stato NON li distingue da un link
# sano. Nelle email servono indirizzi senza scadenza, perche' il testo resta in
# circolo per settimane e il recall lo riallega sotto il messaggio originale.
#
# Finché è vuoto, mailer.run_send/do_test bloccano l'invio delle email che lo citano.
LINK_MAPPATURA = os.getenv(
    "LINK_MAPPATURA",
    "https://schoenbech.com/aree-di-lavoro#:~:text=in%20quel%20mercato%3F-,Esempi%20di%20analisi,-Due%20casi%20reali",
).strip()

# Esempi diretti (link aperti) citati nell'email
LINK_SAMPLE_TECNICO = os.getenv(
    "LINK_SAMPLE_TECNICO",
    "https://businessintelligence.schoenbech.com/accesso/rQaduNZVYMeBFxZFGm5jQTNgkwkjLWZw",
).strip()
LINK_SAMPLE_PRICING = os.getenv(
    "LINK_SAMPLE_PRICING",
    "https://businessintelligence.schoenbech.com/accesso/znZBQnsnMU-x7c8IhkVIWttXKIA3iNk-",
).strip()

_STATIC_LOGO = Path(__file__).resolve().parent.parent / "static" / "logo_email.png"
_WIN_LOGO = Path(r"C:\Users\Luca R\Downloads\sviluppo schoenbech\logo_schoenbech.png")
LOGO = _STATIC_LOGO if _STATIC_LOGO.exists() else _WIN_LOGO

SUBJECT = "Mappatura di mercato e competenze — {TECNOLOGIA}"

# L'etichetta ripete quella della firma e del sito (TALENT SOURCING
# ADVISORY): apertura, firma e sito dicono la stessa cosa, invece di
# presentare due qualifiche diverse nella stessa email.
APERTURA_BASE = "sono Luca Roberto Schoenbech, Talent Sourcing Advisor"

CORPO = """Attraverso filiere diverse di proposito: le stesse competenze su {TECNOLOGIA} pesano in modo diverso {FILIERE_ESEMPIO}, e questo si riconosce solo avendole viste in più contesti. È un punto di osservazione da affiancare a quello che avete dall’interno.

Dove serve, la ricerca di una persona è uno degli esiti possibili, non il presupposto.

Due esempi reali sono consultabili su {LINK_MAPPATURA|schoenbech.com/aree-di-lavoro}: le mappature di un {LINK_TECNICO|Tecnico Area Professional} e di un {LINK_PRICING|Responsabile Pricing} — dove si trovano le competenze, come sono organizzate le funzioni in aziende comparabili, quali riferimenti retributivi emergono. Dati anonimizzati a tutela del cliente e dei professionisti coinvolti, accesso diretto senza registrazione.

Se c’è una funzione su cui il mercato vi sembra più stretto del previsto, o una struttura che vi domandate come sia organizzata altrove, da lì si può partire. Le propongo una call breve, quando Le è comodo."""

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


# Connettori del vecchio "gancio" (frase lunga): non sono profili, non vanno in apertura.
_GANCIO_LEGACY = ("dove ", "in cui ", "ambito in cui", "ambiti ", "settori ", "contesti ",
                  "una fase ", "fase in cui", "nei quali ")


def _profili(gancio):
    g = str(gancio).strip().rstrip(".")
    basso = g.lower()
    if not g or len(g.split()) > 24 or any(c in basso for c in _GANCIO_LEGACY):
        return ""
    prefissi = ("i profili di ", "il profilo di ", "profili di ", "i profili ",
                "profili ", "il profilo ", "di ")
    cambiato = True
    while cambiato:
        cambiato = False
        basso = g.lower()
        for p in prefissi:
            if basso.startswith(p):
                g = g[len(p):].strip()
                cambiato = True
                break
    return g


def _settore(contesto):
    c = str(contesto).strip().rstrip(".")
    for pref in ("nel settore ", "al mondo ", "settore "):
        if c.lower().startswith(pref):
            c = c[len(pref):]
    return c


def apertura_parti(contesto, gancio):
    """(profili, settore) puliti per la frase d'apertura."""
    return _profili(gancio), _settore(contesto)


_ARTICOLI = sorted(("dello ", "della ", "delle ", "degli ", "dei ", "del ", "dell'", "dell\u2019",
                    "di ", "nei ", "negli ", "nella ", "nel ", "al ", "ai ", "agli ", "alla ",
                    "allo "), key=len, reverse=True)


def _filiere_items(contesto):
    """Elenco di filiere senza articoli: 'degli imballaggi..., della chimica' -> ['imballaggi...', 'chimica']."""
    items = []
    for parte in str(contesto or "").split(","):
        c = parte.strip().rstrip(".")
        for p in _ARTICOLI:
            if c.lower().startswith(p):
                c = c[len(p):]
                break
        if c:
            items.append(c)
    return items


def _filiere_list(contesto):
    return ", ".join(_filiere_items(contesto))


def _filiere_esempi(contesto):
    items = _filiere_items(contesto)[:3]
    if not items:
        return "a seconda della filiera in cui si applicano"
    if len(items) == 1:
        return f"in {items[0]} e in filiere vicine"
    if len(items) == 2:
        return f"in {items[0]} o in {items[1]}"
    return f"in {items[0]}, in {items[1]} o in {items[2]}"


def _tecnologia(row):
    t = str(row.get("tecnologia") or "").strip()
    return t or settore_breve(row.get("contesto", ""))


def _sostituisci_dati(testo, row):
    t = str(testo)
    if "{TECNOLOGIA}" in t:
        t = t.replace("{TECNOLOGIA}", _tecnologia(row))
    if "{FILIERE_ESEMPIO}" in t:
        t = t.replace("{FILIERE_ESEMPIO}", _filiere_esempi(row.get("contesto", "")))
    return t


def settore_breve(contesto):
    """Settore in forma corta, per l'oggetto: 'del packaging e converting, ...' -> 'packaging e converting'."""
    c = _settore(contesto)
    prefissi = sorted(("della ", "dello ", "delle ", "degli ", "dei ", "del ", "dell'",
                       "dell\u2019", "di ", "nei ", "negli ", "nella ", "nel ", "al ",
                       "ai ", "agli ", "alla ", "allo "), key=len, reverse=True)
    for p in prefissi:
        if c.lower().startswith(p):
            c = c[len(p):]
            break
    return c.split(",")[0].strip()[:60]


def build_apertura(contesto, gancio, esc=lambda x: x):
    """'sono Luca Roberto Schoenbech. Lavoro sui mercati professionali dell'industria: <filiere>. Dialogo con <funzioni>.'"""
    profili, _ = apertura_parti(contesto, gancio)
    filiere = _filiere_list(contesto)
    frasi = [APERTURA_BASE + "."]
    if filiere:
        frasi.append(f"Lavoro sui mercati professionali dell'industria: {esc(filiere)}.")
    if profili:
        frasi.append(f"Dialogo con {esc(profili)}.")
    return " ".join(frasi)


def _plain(testo):
    return str(testo).replace("**", "")


# Indirizzi che NON devono finire in un'email: link di accesso a tempo della
# piattaforma BI. Scadono da soli e, scaduti, rispondono 200 con una pagina di
# errore, quindi nessun controllo sullo stato HTTP li smaschera.
_URL_SCADENTI = re.compile(
    r"https?://businessintelligence\.schoenbech\.com/\S*", re.I)


def normalizza_link(testo):
    """Converte gli indirizzi a scadenza nel segnaposto {LINK_MAPPATURA}.

    Vale ovunque si trovino: nel testo salvato da /testo, nei default di
    fabbrica, in un testo incollato oggi. Da qui in poi l'indirizzo lo decide
    una sola fonte, la variabile LINK_MAPPATURA, e aggiornarla sistema tutte
    le email, quelle gia' scritte e quelle future.
    """
    if not testo:
        return testo
    t = str(testo)
    # I due esempi diretti hanno un segnaposto proprio: non vanno riscritti
    # come link di mappatura generico.
    if LINK_SAMPLE_TECNICO:
        t = t.replace(LINK_SAMPLE_TECNICO, "{LINK_TECNICO}")
    if LINK_SAMPLE_PRICING:
        t = t.replace(LINK_SAMPLE_PRICING, "{LINK_PRICING}")
    return _URL_SCADENTI.sub("{LINK_MAPPATURA}", t)


# Il paragrafo storico prometteva UN solo caso ("un esempio reale di mappatura,
# relativo alla ricerca di un Responsabile Pricing"). La pagina pubblica ne
# offre due, quindi va sostituito ovunque, anche nei testi gia' salvati da
# /testo: altrimenti l'email continua a promettere il caso singolo mentre il
# link porta alla pagina con entrambi.
PARAGRAFO_ESEMPI = (
    "Due esempi reali sono consultabili su {LINK_MAPPATURA|schoenbech.com/aree-di-lavoro}: "
    "le mappature di un {LINK_TECNICO|Tecnico Area Professional} e di un "
    "{LINK_PRICING|Responsabile Pricing} \u2014 dove si trovano le competenze, come sono "
    "organizzate le funzioni in aziende comparabili, quali riferimenti retributivi "
    "emergono. Dati anonimizzati a tutela del cliente e dei professionisti coinvolti, "
    "accesso diretto senza registrazione."
)

# Tracce del vecchio paragrafo. Si interviene solo su un paragrafo che cita il
# segnaposto E una di queste: un paragrafo riscritto da te non viene toccato.
_TRACCE_VECCHIE = re.compile(
    r"Responsabile Pricing|esempio reale di mappatura|due esempi reali di analisi", re.I)


def aggiorna_paragrafo_esempi(testo):
    """Sostituisce il paragrafo che promette un solo esempio di mappatura.

    Lavora per paragrafi (separati da riga vuota) e conserva il resto del
    testo come sta, separatori compresi.
    """
    if not testo:
        return testo
    parti = re.split(r"(\n\s*\n)", str(testo))
    for i, par in enumerate(parti):
        if "LINK_MAPPATURA" in par and _TRACCE_VECCHIE.search(par):
            parti[i] = PARAGRAFO_ESEMPI
    return "".join(parti)


def normalizza_testo(testo):
    """Tutte le correzioni strutturali sul testo di un'email, in un punto solo."""
    return aggiorna_paragrafo_esempi(normalizza_link(testo))


def get_email_template():
    """Testo generale (oggetto, corpo, recall) da DB, con default di fabbrica.

    Passaggio obbligato di anteprima, test, invio e recall: la normalizzazione
    dei link sta qui, cosi' nessuna via la salta.
    """
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
    tpl["corpo"] = normalizza_testo(tpl["corpo"])
    tpl["recall_text"] = normalizza_testo(tpl["recall_text"])
    return tpl


# Segnaposto link: {LINK}, {LINK_BREVE}, {LINK_MAPPATURA}, oppure con il testo
# cliccabile scelto: {LINK|etichetta}, {LINK_MAPPATURA|etichetta}.
_LINK_RE = re.compile(
    r"[{](LINK_MAPPATURA|LINK_TECNICO|LINK_PRICING|LINK_BREVE|LINK)(?:[|]([^{}]+))?[}]")


def _url(nome):
    return {"LINK_MAPPATURA": LINK_MAPPATURA, "LINK_TECNICO": LINK_SAMPLE_TECNICO,
            "LINK_PRICING": LINK_SAMPLE_PRICING}.get(nome, LINK)


def link_mancanti(tpl=None):
    """Segnaposto usati nel testo ma senza URL configurato (invio da bloccare)."""
    t = tpl or {}
    testi = " ".join([t.get("corpo") or CORPO, t.get("recall_text") or RECALL_TEXT])
    mancanti = []
    for m in _LINK_RE.finditer(testi):
        nome = m.group(1)
        if nome not in ("LINK", "LINK_BREVE") and not _url(nome):
            mancanti.append(nome)
    return sorted(set(mancanti))


def _sostituisci_link_plain(testo):
    def sub(m):
        url = _url(m.group(1)) or "[link esempio di mappatura]"
        return f"{m.group(2).strip()} ({url})" if m.group(2) else url
    return _LINK_RE.sub(sub, testo)


def build_email(row, message_no=1, tpl=None):
    t = tpl or {}
    subject = t.get("subject") or SUBJECT
    if "{TECNOLOGIA}" in subject:
        tec = _tecnologia(row)
        if tec:
            subject = subject.replace("{TECNOLOGIA}", tec)
        else:
            subject = (subject.replace(" \u2014 {TECNOLOGIA}", "")
                       .replace("{TECNOLOGIA}", "").strip(" \u2014\u2013-"))
    if "{SETTORE}" in subject:
        breve = settore_breve(row.get("contesto", ""))
        if breve:
            subject = subject.replace("{SETTORE}", breve)
        else:
            subject = subject.replace(" \u2014 {SETTORE}", "").replace("{SETTORE}", "").strip(" \u2014\u2013-")
    corpo = _sostituisci_link_plain(_plain(_sostituisci_dati(t.get("corpo") or CORPO, row)))
    recall = _sostituisci_link_plain(_plain(_sostituisci_dati(t.get("recall_text") or RECALL_TEXT, row)))
    saluto = row.get("saluto", "")
    appiglio = str(row.get("appiglio") or "").strip()
    # Apertura ricalcolata da contesto/gancio: testo semplice identico all'HTML
    # (paragrafo_apertura salvato all'import resta solo come fallback).
    apertura = _plain(build_apertura(row.get("contesto", ""), row.get("gancio", "")))
    buongiorno = saluto_orario()
    ricordato = row.get("saluto_originale") or buongiorno
    testa = f"{appiglio}\n\n" if appiglio else ""
    corpo_orig = f"{testa}{apertura}\n\n{corpo}\n\n{CLOSING}\n{FIRMA_NOME}\n\n{PRIVACY}"
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
    apertura = build_apertura(contesto, gancio,
                              esc=lambda x: f"<strong>{html.escape(x)}</strong>")
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", apertura)


LINK_ANCHOR = (f'<a href="{LINK}" style="color:#b08d57;font-weight:bold;text-decoration:none;">'
               "Presentazione Attivit&agrave; di Consulenza &mdash; Overview</a>")

LINK_ANCHOR_BREVE = (f'<a href="{LINK}" style="color:#b08d57;font-weight:bold;text-decoration:none;">'
                     "la mia presentazione</a>")


_ETICHETTE_LINK = {"LINK_MAPPATURA": "Presentazione Attivit&agrave; di Mappatura",
                   "LINK_TECNICO": "Tecnico Area Professional",
                   "LINK_PRICING": "Responsabile Pricing"}


def _link_html(nome, etichetta=None):
    url = _url(nome)
    testo = (etichetta or "").strip() or _ETICHETTE_LINK.get(nome, "")
    if not url:
        return f"[{testo}]"
    return (f'<a href="{html.escape(url, quote=True)}" '
            f'style="color:#b08d57;font-weight:bold;text-decoration:none;">{testo}</a>')


def _sostituisci_link_html(testo):
    """Segnaposto -> link dorati (l'etichetta è già escapata insieme al paragrafo)."""
    def sub(m):
        nome, etichetta = m.group(1), m.group(2)
        if nome in ("LINK_MAPPATURA", "LINK_TECNICO", "LINK_PRICING"):
            return _link_html(nome, etichetta)
        if etichetta:
            return (f'<a href="{LINK}" style="color:#b08d57;font-weight:bold;text-decoration:none;">'
                    f"{etichetta.strip()}</a>")
        return LINK_ANCHOR_BREVE if nome == "LINK_BREVE" else LINK_ANCHOR
    return _LINK_RE.sub(sub, testo)


def _corpo_html(corpo):
    paragrafi = [p.strip() for p in str(corpo).replace("\r\n", "\n").split("\n\n") if p.strip()]
    link_html = LINK_ANCHOR
    out = []
    for p in paragrafi:
        p = html.escape(p)
        p = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", p, flags=re.S)
        p = _sostituisci_link_html(p.replace(chr(10), " "))
        out.append(f'<p style="margin:0 0 22px 0;">{p}</p>')
    return "".join(out)


def build_email_html(row, logo="/logo.png", message_no=1, tpl=None):
    t = tpl or {}
    intro_p = f'<p style="margin:0 0 20px 0;">{_intro_html(row.get("contesto", ""), row.get("gancio", ""))}</p>'
    corpo = _corpo_html(_sostituisci_dati(t.get("corpo") or CORPO, row))
    saluto = str(row.get("saluto", ""))
    appiglio = str(row.get("appiglio") or "").strip()
    # La pagina costruita qui NON si chiama "html": in questa funzione serve il
    # modulo html per l'escape dell'appiglio, e una variabile con lo stesso nome
    # lo renderebbe inaccessibile. Con l'appiglio compilato la costruzione
    # falliva, l'invio registrava un errore e la riga restava bruciata.
    appiglio_p = (f'<p style="margin:0 0 20px 0;">{html.escape(appiglio)}</p>'
                  if appiglio else "")
    if message_no == 2:
        ricordato = row.get("saluto_originale") or saluto_orario()
        recall = (_sostituisci_dati(_plain(t.get("recall_text") or RECALL_TEXT), row)
                  .replace(chr(10), "<br>"))
        recall = _sostituisci_link_html(recall)
        pagina = (HTML_TOP
                  + f'<p style="margin:0 0 20px 0;">{recall}</p></div>'
                  + HTML_FIRMA
                  + '<div style="font-size:16px;line-height:1.65;margin-left:10px;max-width:680px;margin-top:18px;">'
                  + '<hr style=\'border:0;border-top:1px solid #ccc;margin:16px 0\'>'
                  + '<p style="margin:0 0 20px 0;"><b>----- MESSAGGIO ORIGINALE -----</b></p>'
                  + f'<p style="margin:0 0 20px 0;">{saluto}, {ricordato},</p>'
                  + appiglio_p + intro_p + corpo + HTML_SALUTI + "</div>"
                  + HTML_FIRMA
                  + HTML_FOOTER)
    else:
        pagina = HTML_TOP + appiglio_p + intro_p + corpo + HTML_CHIUSURA + HTML_FIRMA + HTML_FOOTER
    return (pagina
            .replace("__SALUTO__", saluto)
            .replace("__BUONGIORNO__", saluto_orario())
            .replace("__LOGO__", logo))
