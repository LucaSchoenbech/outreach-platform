# -*- coding: utf-8 -*-
"""Configurazione applicazione — legge le variabili da .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _get(key, default=""):
    return os.getenv(key, default)


def _get_int(key, default=0):
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


DATABASE_URL = _get("DATABASE_URL")
DB_SCHEMA = _get("DB_SCHEMA", "mass")

SECRET_KEY = _get("SECRET_KEY", "dev-secret-change-me")
ADMIN_USER = _get("ADMIN_USER", "luca@schoenbech.com")
ADMIN_PASSWORD = _get("ADMIN_PASSWORD", "admin")

SENDER_EMAIL = _get("SENDER_EMAIL", "luca@schoenbech.com")
SENDER_NAME = _get("SENDER_NAME", "Schoenbech • Talent Advisory")
REPLY_TO = _get("REPLY_TO", SENDER_EMAIL)

SMTP_SERVER = _get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = _get_int("SMTP_PORT", 465)
SMTP_PASSWORD = _get("SMTP_PASSWORD")
IMAP_SERVER = _get("IMAP_SERVER", "imap.gmail.com")
IMAP_PORT = _get_int("IMAP_PORT", 993)

ARUBA_SMTP_SERVER = _get("ARUBA_SMTP_SERVER", "smtps.aruba.it")
ARUBA_SMTP_PORT = _get_int("ARUBA_SMTP_PORT", 465)
ARUBA_IMAP_SERVER = _get("ARUBA_IMAP_SERVER", "imaps.aruba.it")
ARUBA_IMAP_PORT = _get_int("ARUBA_IMAP_PORT", 993)
ARUBA_EMAIL = _get("ARUBA_EMAIL", SENDER_EMAIL)
ARUBA_PASSWORD = _get("ARUBA_PASSWORD")

DELAY_MIN = _get_int("DELAY_MIN", 65)
DELAY_MAX = _get_int("DELAY_MAX", 115)
BREAK_MIN = _get_int("BREAK_MIN", 150)
BREAK_MAX = _get_int("BREAK_MAX", 240)
PAUSE_EVERY = _get_int("PAUSE_EVERY", 10)

APP_HOST = _get("APP_HOST", "127.0.0.1")
APP_PORT = _get_int("APP_PORT", 8788)

# --- DeepSeek (provider AI principale) ---
DEEPSEEK_API_KEY = _get("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = _get("DEEPSEEK_MODEL", "deepseek-v4.1-flash")
DEEPSEEK_MODEL_FALLBACKS = _get("DEEPSEEK_MODEL_FALLBACKS", "deepseek-chat")

# --- Gemini (fallback) ---
GEMINI_API_KEY = _get("GEMINI_API_KEY")
GEMINI_MODEL = _get("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_MODEL_FALLBACKS = _get(
    "GEMINI_MODEL_FALLBACKS", "gemini-3.6-flash,gemini-flash-lite-latest,gemini-2.5-flash")
GEMINI_THINKING = _get("GEMINI_THINKING", "medium")
