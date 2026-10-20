# -*- coding: utf-8 -*-
"""Invio programmato guidato dall'esterno (Cloud Scheduler).

Perche' non un thread: su Cloud Run il servizio gira con --cpu-throttling e
--min-instances 0, quindi fra una richiesta e l'altra la CPU viene tolta e
l'istanza spenta. Un invio da un'ora in un thread di sfondo non arriverebbe
mai in fondo, e nessuno se ne accorgerebbe.

Come funziona invece: Cloud Scheduler chiama /scheduler/tick ogni paio di
minuti dentro la finestra oraria. Ogni chiamata spedisce AL PIU' UNA email e
torna subito. Il ritmo umano resta quello di sempre (DELAY_MIN..DELAY_MAX fra
due invii, BREAK_MIN..BREAK_MAX ogni PAUSE_EVERY), ma l'attesa e' custodita a
database invece che in un `sleep`: la riga scheduler_state dice quando e'
lecito spedire la prossima.

Ordine di precedenza: prima i primi invii (auto_send), poi i richiami
(auto_recall). Le campagne si esauriscono da sole: quando non restano righe,
il flag viene spento.
"""
import random
from datetime import datetime, timedelta, timezone

from app import config, mailer


def _stato(db, models):
    st = db.get(models.SchedulerState, 1)
    if not st:
        st = models.SchedulerState(state_id=1, inviate_blocco=0)
        db.add(st)
        db.flush()
    return st


def _prossima_attesa(inviate_blocco):
    """Secondi da aspettare prima del prossimo invio, col ritmo configurato."""
    if config.PAUSE_EVERY and inviate_blocco and inviate_blocco % config.PAUSE_EVERY == 0:
        return random.randint(config.BREAK_MIN, config.BREAK_MAX)
    return random.randint(config.DELAY_MIN, config.DELAY_MAX)


def tick(forza_finestra=False):
    """Esegue un colpo: al piu' una email. Ritorna un riepilogo leggibile.

    `forza_finestra` ignora l'orario: serve solo alle prove, mai in produzione.
    """
    from app import models
    from app.db import SessionLocal
    from app.main import _ready_rows, _recall_rows

    adesso = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        st = _stato(db, models)

        if not forza_finestra and not mailer.nella_finestra():
            return {"inviata": False, "motivo": "fuori finestra",
                    "finestra": f"{config.SEND_WINDOW_START}-{config.SEND_WINDOW_END}"}
        if mailer.tetto_raggiunto():
            return {"inviata": False, "motivo": "tetto giornaliero raggiunto",
                    "inviate_oggi": mailer.inviate_oggi(), "tetto": config.DAILY_LIMIT}
        if st.next_at and adesso < st.next_at:
            manca = int((st.next_at - adesso).total_seconds())
            return {"inviata": False, "motivo": "pausa fra due invii",
                    "riprende_fra_secondi": manca}

        # Prima i primi invii, poi i richiami.
        scelta = None
        for flag, estrai, numero in (("auto_send", _ready_rows, 1),
                                     ("auto_recall", _recall_rows, 2)):
            for camp in db.query(models.Campaign).filter_by(**{flag: True}).all():
                righe = estrai(db, camp)
                if not righe:
                    setattr(camp, flag, False)   # campagna esaurita: si spegne da sola
                    db.commit()
                    continue
                scelta = (camp, righe[0], numero)
                break
            if scelta:
                break

        if not scelta:
            return {"inviata": False, "motivo": "nessuna campagna programmata con righe da inviare"}

        camp, riga, numero = scelta
        esito = mailer.send_singolo(riga, camp.channel, salva_copia=True, message_no=numero)
        riuscita = esito.lower().startswith("email inviata")

        st = _stato(db, models)
        st.inviate_blocco = (st.inviate_blocco or 0) + 1 if riuscita else (st.inviate_blocco or 0)
        st.next_at = adesso + timedelta(seconds=_prossima_attesa(st.inviate_blocco))
        st.ultimo_esito = f"{riga.get('email', '')}: {esito}"[:400]
        db.commit()

        return {"inviata": riuscita, "destinatario": riga.get("email", ""),
                "azienda": riga.get("azienda", ""), "campagna": camp.name,
                "tipo": "richiamo" if numero == 2 else "primo invio",
                "esito": esito, "prossima_alle": st.next_at.isoformat(),
                "inviate_oggi": mailer.inviate_oggi()}
    finally:
        db.close()


def stato_pubblico():
    """Riepilogo per l'interfaccia: cosa e' programmato e a che punto siamo."""
    from app import models
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        st = db.get(models.SchedulerState, 1)
        campagne = db.query(models.Campaign).filter(
            (models.Campaign.auto_send.is_(True)) | (models.Campaign.auto_recall.is_(True))).all()
        return {
            "programmate": [{"nome": c.name, "primi_invii": bool(c.auto_send),
                             "richiami": bool(c.auto_recall)} for c in campagne],
            "prossima_alle": st.next_at.isoformat() if st and st.next_at else None,
            "ultimo_esito": (st.ultimo_esito if st else None) or "",
            "nella_finestra": mailer.nella_finestra(),
            "inviate_oggi": mailer.inviate_oggi(),
            "tetto": config.DAILY_LIMIT,
        }
    finally:
        db.close()
