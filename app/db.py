# -*- coding: utf-8 -*-
"""Connessione database (SQLAlchemy 2.0) + Base con schema dedicato `mass`."""
from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

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
