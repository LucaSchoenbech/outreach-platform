# -*- coding: utf-8 -*-
"""Modelli dell'app di outreach massivo.

Tabelle proprie nello schema dedicato `mass` (vedi app/db.py), nello stesso
database `outreach`. NON toccano le tabelle `outreach_*` dell'app esistente
`cv-scouting-lusha`.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text,
    UniqueConstraint, Uuid, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Company(Base):
    __tablename__ = "company"

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    company_uid: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=_uuid, nullable=False)
    legal_name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str] = mapped_column(Text, nullable=False)
    vat: Mapped[str | None] = mapped_column(Text)
    domain: Mapped[str | None] = mapped_column(Text)
    sector: Mapped[str | None] = mapped_column(Text)
    hq_location: Mapped[str | None] = mapped_column(Text)
    suppression: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    suppression_reason: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    contacts: Mapped[list["Contact"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    campaign_companies: Mapped[list["CampaignCompany"]] = relationship(back_populates="company")


class Contact(Base):
    __tablename__ = "contact"

    contact_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("company.company_id", ondelete="CASCADE"), nullable=False)
    first_name: Mapped[str | None] = mapped_column(Text)
    last_name: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    email_normalized: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(Text)
    opt_out: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    opt_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    company: Mapped["Company"] = relationship(back_populates="contacts")

    __table_args__ = (UniqueConstraint("company_id", "email_normalized", name="ux_contact_email"),)


class Campaign(Base):
    __tablename__ = "campaign"

    campaign_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="active", nullable=False)
    channel: Mapped[str] = mapped_column(Text, default="Gmail", nullable=False)
    created_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    campaign_companies: Mapped[list["CampaignCompany"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")


class CampaignCompany(Base):
    __tablename__ = "campaign_company"

    campaign_company_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("campaign.campaign_id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("company.company_id"), nullable=False)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contact.contact_id"))
    status: Mapped[str] = mapped_column(Text, default="discovered", nullable=False)

    draft_status: Mapped[str] = mapped_column(Text, default="Bozza", nullable=False)  # Bozza|Pronta|Esclusa
    contesto: Mapped[str | None] = mapped_column(Text)
    gancio: Mapped[str | None] = mapped_column(Text)
    tipo_gancio: Mapped[str | None] = mapped_column(Text)
    timing: Mapped[str | None] = mapped_column(Text)
    flag: Mapped[str | None] = mapped_column(Text)
    saluto: Mapped[str | None] = mapped_column(Text)
    paragrafo_apertura: Mapped[str | None] = mapped_column(Text)
    fonti: Mapped[str | None] = mapped_column(Text)

    # dati di ricerca (input per la generazione AI)
    ricerca_attivita: Mapped[str | None] = mapped_column(Text)
    ricerca_competenze: Mapped[str | None] = mapped_column(Text)
    ricerca_segnale: Mapped[str | None] = mapped_column(Text)
    alert_text: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    campaign: Mapped["Campaign"] = relationship(back_populates="campaign_companies")
    company: Mapped["Company"] = relationship(back_populates="campaign_companies")

    __table_args__ = (UniqueConstraint("campaign_id", "company_id", name="ux_cc"),)


class OutreachMessage(Base):
    __tablename__ = "outreach_message"

    message_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    campaign_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    campaign_company_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    message_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    channel: Mapped[str] = mapped_column(Text, default="gmail", nullable=False)
    to_email: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="queued", nullable=False)
    dedupe_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutreachEvent(Base):
    __tablename__ = "outreach_event"

    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    company_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    message_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    payload: Mapped[dict | None] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FollowUp(Base):
    __tablename__ = "follow_up"

    follow_up_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    campaign_company_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    sequence_no: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, default="scheduled", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmailTemplate(Base):
    __tablename__ = "email_template"

    template_id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    subject: Mapped[str | None] = mapped_column(Text)
    corpo: Mapped[str | None] = mapped_column(Text)
    recall_text: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Suppression(Base):
    __tablename__ = "suppression"

    suppression_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(Text, nullable=False)  # email | domain
    value: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("kind", "value", name="ux_suppression"),)
