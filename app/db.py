# -*- coding: utf-8 -*-
"""Connessione database (SQLAlchemy 2.0) + Base con schema dedicato `mass`."""
from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import DATABASE_URL, DB_SCHEMA

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL mancante. Copia .env.example in .env e imposta la stringa di connessione."
    )

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True,
    connect_args={"connect_timeout": 10},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    metadata = MetaData(schema=DB_SCHEMA)


def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema():
    """Crea lo schema dedicato se non esiste (non tocca lo schema esistente)."""
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{DB_SCHEMA}"'))


def init_db():
    """Crea schema + tabelle dell'app (idempotente)."""
    ensure_schema()
    import app.models  # noqa: F401  (registra i modelli)
    Base.metadata.create_all(engine)
    # Migrazione: consente più interlocutori della stessa azienda nella stessa campagna.
    try:
        with engine.begin() as conn:
            conn.execute(text(f'ALTER TABLE "{DB_SCHEMA}".campaign_company '
                              "DROP CONSTRAINT IF EXISTS ux_cc"))
    except Exception:
        pass
    # Migrazione: flag di programmazione invio automatico sulla campagna.
    try:
        with engine.begin() as conn:
            conn.execute(text(f'ALTER TABLE "{DB_SCHEMA}".campaign '
                              "ADD COLUMN IF NOT EXISTS auto_send BOOLEAN NOT NULL DEFAULT FALSE"))
    except Exception:
        pass
    # Migrazione: memoria della proposta AI (per riconoscere le correzioni manuali),
    # motivo di esclusione e apertura realmente inviata.
    for tabella, colonne in (
        ("campaign_company", ("contesto_ai TEXT", "gancio_ai TEXT", "escluso_motivo TEXT")),
        ("outreach_message", ("contesto TEXT", "gancio TEXT", "message_id_header TEXT")),
        ("contact", ("risposto_at TIMESTAMPTZ", "risposta_oggetto TEXT",
                     "risposta_da TEXT")),
        ("campaign", ("auto_recall BOOLEAN NOT NULL DEFAULT FALSE",)),
    ):
        for colonna in colonne:
            try:
                with engine.begin() as conn:
                    conn.execute(text(f'ALTER TABLE "{DB_SCHEMA}".{tabella} '
                                      f"ADD COLUMN IF NOT EXISTS {colonna}"))
            except Exception:
                pass
    # Bonifica una tantum del testo salvato da /testo: indirizzi a scadenza ->
    # segnaposto, e paragrafo che promette un solo esempio -> i due casi della
    # pagina pubblica. Cosi' la modifica vale su TUTTE le email, comprese
    # quelle che usano un testo salvato mesi fa, senza doverlo riscrivere a
    # mano. Idempotente: a regime non trova piu' nulla da cambiare.
    try:
        from app import models
        from app.email_builder import normalizza_testo
        with Session(engine) as ses:
            row = ses.get(models.EmailTemplate, 1)
            if row:
                nuovo_corpo = normalizza_testo(row.corpo)
                nuovo_recall = normalizza_testo(row.recall_text)
                if nuovo_corpo != row.corpo or nuovo_recall != row.recall_text:
                    row.corpo, row.recall_text = nuovo_corpo, nuovo_recall
                    ses.commit()
    except Exception:
        pass

    # Indice per l'aggancio delle risposte via In-Reply-To/References.
    try:
        with engine.begin() as conn:
            conn.execute(text(
                f'CREATE INDEX IF NOT EXISTS ix_outreach_message_msgid '
                f'ON "{DB_SCHEMA}".outreach_message (message_id_header)'))
    except Exception:
        pass
