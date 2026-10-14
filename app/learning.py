# -*- coding: utf-8 -*-
"""Memoria operativa: correzioni manuali e contatti gia' raggiunti.

Due funzioni distinte:

1) CORREZIONI — quando l'operatore corregge a mano settore/profili prodotti
   dall'AI, la coppia "proposta -> correzione" viene salvata con i dati di
   ricerca di partenza. Le correzioni diventano esempi nel prompt delle
   generazioni successive.

   Regola voluta: una correzione vale solo per i file caricati DOPO di essa,
   mai per il lavoro gia' in corso. Per questo gli esempi sono sempre filtrati
   sulla data di import della riga (`CampaignCompany.created_at`): una riga
   usa solo le correzioni registrate prima del proprio ingresso in campagna.

2) GIA' CONTATTATI — ricerca degli invii riusciti verso lo stesso indirizzo in
   campagne precedenti, per non scrivere due volte alla stessa persona.
"""
import re

from sqlalchemy import func

MAX_ESEMPI = 12          # esempi al massimo nel prompt (tiene la richiesta corta)
MAX_DATI_CHAR = 220      # troncamento del riassunto dei dati di ricerca


def _norm(v):
    """Normalizza per confronto: spazi compattati, minuscole, senza punti finali."""
    return re.sub(r"\s+", " ", (v or "").strip().lower()).strip(" .;,")


def _riassunto_dati(cc):
    """Riassunto compatto dei dati di ricerca di una riga, per l'esempio."""
    parti = []
    for etichetta, valore in (("attivita", cc.ricerca_attivita),
                              ("competenze", cc.ricerca_competenze),
                              ("segnale", cc.ricerca_segnale),
                              ("alert", cc.alert_text)):
        testo = re.sub(r"\s+", " ", (valore or "").strip())
        if testo:
            parti.append(f"{etichetta}: {testo}")
    riassunto = " | ".join(parti)
    if len(riassunto) > MAX_DATI_CHAR:
        riassunto = riassunto[:MAX_DATI_CHAR].rstrip() + "..."
    return riassunto


def registra_correzione(db, cc, contesto_nuovo, gancio_nuovo, azienda=""):
    """Salva la correzione manuale di una riga, se c'e' davvero una differenza.

    Va chiamata PRIMA di sovrascrivere `cc.contesto` / `cc.gancio`.
    Ritorna True se ha registrato qualcosa.
    """
    from app import models
    ai_ctx, ai_gan = (cc.contesto_ai or "").strip(), (cc.gancio_ai or "").strip()
    if not ai_ctx and not ai_gan:
        return False  # nessuna proposta AI da confrontare: non e' una correzione
    nuovo_ctx, nuovo_gan = (contesto_nuovo or "").strip(), (gancio_nuovo or "").strip()
    if not nuovo_ctx and not nuovo_gan:
        return False
    if _norm(ai_ctx) == _norm(nuovo_ctx) and _norm(ai_gan) == _norm(nuovo_gan):
        return False  # approvata senza modifiche: niente da imparare
    db.add(models.AiCorrection(
        campaign_company_id=cc.campaign_company_id,
        company_id=cc.company_id,
        azienda=(azienda or "").strip() or None,
        dati_ricerca=_riassunto_dati(cc) or None,
        contesto_ai=ai_ctx or None, gancio_ai=ai_gan or None,
        contesto_corretto=nuovo_ctx or None, gancio_corretto=nuovo_gan or None))
    return True


def carica_correzioni(db):
    """Tutte le correzioni, dalla piu' recente. Lista piccola: si filtra in memoria."""
    from app import models
    return (db.query(models.AiCorrection)
            .order_by(models.AiCorrection.created_at.desc())
            .limit(400).all())


def esempi_validi(correzioni, cutoff):
    """Correzioni utilizzabili per una riga importata a `cutoff`.

    Tiene solo quelle registrate PRIMA di `cutoff` (il lavoro in corso non
    viene toccato), scarta i doppioni e si ferma a MAX_ESEMPI.
    """
    if cutoff is None:
        return []
    scelti = []
    viste = set()
    for c in correzioni:
        if c.created_at is None or c.created_at >= cutoff:
            continue
        chiave = (_norm(c.contesto_corretto), _norm(c.gancio_corretto),
                  _norm(c.contesto_ai), _norm(c.gancio_ai))
        if chiave in viste:
            continue
        viste.add(chiave)
        scelti.append(c)
        if len(scelti) >= MAX_ESEMPI:
            break
    return scelti


def blocco_prompt(esempi):
    """Blocco da aggiungere al prompt AI con le correzioni dell'operatore."""
    if not esempi:
        return ""
    righe = [
        "",
        "CORREZIONI PRECEDENTI DELL'OPERATORE (PRIORITA' MASSIMA):",
        "Sono casi reali in cui una tua proposta e' stata corretta a mano. Capisci",
        "il criterio della correzione (lessico, livello di dettaglio, cosa va nel",
        "settore e cosa nei profili) e applicalo. Non ripetere gli errori corretti.",
        "",
    ]
    for n, c in enumerate(esempi, 1):
        righe.append(f"{n}) Dati: {c.dati_ricerca or '(nessun dato di ricerca)'}")
        righe.append(f'   Avevi proposto -> settore: "{c.contesto_ai or ""}"'
                     f' | profili: "{c.gancio_ai or ""}"')
        righe.append(f'   Corretto in    -> settore: "{c.contesto_corretto or ""}"'
                     f' | profili: "{c.gancio_corretto or ""}"')
    righe.append("")
    righe.append("Queste correzioni prevalgono sugli esempi generici qui sopra.")
    return "\n".join(righe)


def gia_contattato(db, email, campaign_id=None):
    """Primo invio riuscito a questo indirizzo in un'altra campagna.

    Ritorna (data_invio, nome_campagna) oppure None. Confronta sull'indirizzo
    realmente usato, cosi' il controllo regge anche se l'azienda e' duplicata.
    """
    from app import models
    indirizzo = (email or "").strip().lower()
    if not indirizzo:
        return None
    q = (db.query(models.OutreachMessage)
         .filter(models.OutreachMessage.status == "sent")
         .filter(func.lower(models.OutreachMessage.to_email) == indirizzo))
    if campaign_id is not None:
        q = q.filter(models.OutreachMessage.campaign_id != campaign_id)
    msg = q.order_by(models.OutreachMessage.sent_at.asc()).first()
    if not msg:
        return None
    camp = db.get(models.Campaign, msg.campaign_id)
    return msg.sent_at, (camp.name if camp else "")


def conta_correzioni(db):
    from app import models
    return db.query(models.AiCorrection).count()
