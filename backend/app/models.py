from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def uid() -> str:
    return str(uuid4())


def now() -> datetime:
    return datetime.now(timezone.utc)


class Clinic(Base):
    __tablename__ = "clinics"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(200))


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(30), index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    patient_id: Mapped[str | None] = mapped_column(String, nullable=True)


class Patient(Base):
    __tablename__ = "patients"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id"), index=True)
    display_code: Mapped[str] = mapped_column(String(40), index=True)
    name_encrypted: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Interaction(Base):
    __tablename__ = "interactions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id"), index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    author_role: Mapped[str] = mapped_column(String(30))
    interaction_type: Mapped[str] = mapped_column(String(80))
    raw_content_encrypted: Mapped[str] = mapped_column(Text)
    redacted_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    redaction_map_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    synthetic_risk_tag: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class TimelineEntry(Base):
    __tablename__ = "timeline_entries"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id"), index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    interaction_id: Mapped[str | None] = mapped_column(ForeignKey("interactions.id"), nullable=True)
    author_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    author_role: Mapped[str] = mapped_column(String(30))
    entry_type: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(240))
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    __table_args__ = (Index("ix_timeline_patient_created", "patient_id", "created_at"),)


class EntrySection(Base):
    __tablename__ = "entry_sections"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    entry_id: Mapped[str] = mapped_column(ForeignKey("timeline_entries.id"), index=True)
    section_key: Mapped[str] = mapped_column(String(60))
    content: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    visibility: Mapped[str] = mapped_column(String(30), default="internal")
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    __table_args__ = (UniqueConstraint("entry_id", "section_key", name="uq_entry_section"),)


class EntryVersion(Base):
    __tablename__ = "entry_versions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    entry_id: Mapped[str] = mapped_column(ForeignKey("timeline_entries.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    snapshot_json: Mapped[str] = mapped_column(Text)
    changed_section: Mapped[str | None] = mapped_column(String(60), nullable=True)
    changed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("entry_id", "version", name="uq_entry_version"),)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id"), index=True)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(80))
    resource_type: Mapped[str] = mapped_column(String(60))
    resource_id: Mapped[str] = mapped_column(String, index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ProvenanceEdge(Base):
    __tablename__ = "provenance_edges"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    target_type: Mapped[str] = mapped_column(String(50))
    target_id: Mapped[str] = mapped_column(String, index=True)
    source_entry_id: Mapped[str] = mapped_column(ForeignKey("timeline_entries.id"), index=True)
    source_entry_version_id: Mapped[str] = mapped_column(ForeignKey("entry_versions.id"))
    source_section_key: Mapped[str] = mapped_column(String(60), default="raw")
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    original_start_offset: Mapped[int] = mapped_column(Integer)
    original_end_offset: Mapped[int] = mapped_column(Integer)
    quote_hash: Mapped[str] = mapped_column(String(64))
    match_method: Mapped[str] = mapped_column(String(30))
    source_support: Mapped[str] = mapped_column(String(30))


class CommentThread(Base):
    __tablename__ = "comments"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id"), index=True)
    entry_id: Mapped[str] = mapped_column(ForeignKey("timeline_entries.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text)
    mention_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    assigned_to_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ClinicalFact(Base):
    __tablename__ = "clinical_facts"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id"), index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    entry_id: Mapped[str] = mapped_column(ForeignKey("timeline_entries.id"))
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    normalized_value: Mapped[str] = mapped_column(String(300))
    evidence_quote: Mapped[str] = mapped_column(Text)
    provenance_edge_id: Mapped[str] = mapped_column(ForeignKey("provenance_edges.id"))
    status: Mapped[str] = mapped_column(String(30), default="active")
    clinician_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Conflict(Base):
    __tablename__ = "conflicts"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id"), index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    fact_a_id: Mapped[str] = mapped_column(ForeignKey("clinical_facts.id"))
    fact_b_id: Mapped[str] = mapped_column(ForeignKey("clinical_facts.id"))
    status: Mapped[str] = mapped_column(String(30), default="open")
    resolution_fact_id: Mapped[str | None] = mapped_column(ForeignKey("clinical_facts.id"), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Highlight(Base):
    __tablename__ = "highlights"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id"), index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    entry_id: Mapped[str] = mapped_column(ForeignKey("timeline_entries.id"))
    text: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str] = mapped_column(String(50))
    risk_reason: Mapped[str] = mapped_column(String(240), default="No deterministic risk floor")
    risk_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    risk_floor: Mapped[float] = mapped_column(Float, default=0)
    source_support: Mapped[str] = mapped_column(String(30))
    provenance_edge_id: Mapped[str] = mapped_column(ForeignKey("provenance_edges.id"))
    unresolved: Mapped[bool] = mapped_column(Boolean, default=False)
    clinician_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    base_score: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(30), default="suggested")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class GlanceSnapshot(Base):
    __tablename__ = "glance_snapshots"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    viewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    items_json: Mapped[str] = mapped_column(Text, default="[]")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("patient_id", "viewer_id", name="uq_glance_viewer"),)


class EmbeddingRecord(Base):
    __tablename__ = "embeddings"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    owner_type: Mapped[str] = mapped_column(String(40))
    owner_id: Mapped[str] = mapped_column(String, index=True)
    model: Mapped[str] = mapped_column(String(100))
    vector_json: Mapped[str] = mapped_column(Text)


class PreferenceProfile(Base):
    __tablename__ = "preference_profiles"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    clinician_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True)
    positive_vector_json: Mapped[str] = mapped_column(Text, default="[]")
    negative_vector_json: Mapped[str] = mapped_column(Text, default="[]")
    positive_weight: Mapped[float] = mapped_column(Float, default=0)
    negative_weight: Mapped[float] = mapped_column(Float, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)


class FeedbackEvent(Base):
    __tablename__ = "feedback_events"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    highlight_id: Mapped[str] = mapped_column(ForeignKey("highlights.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(30))
    profile_version: Mapped[int] = mapped_column(Integer)
    impression_seen: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    interaction_id: Mapped[str] = mapped_column(ForeignKey("interactions.id"), unique=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class PatientFacingItem(Base):
    __tablename__ = "patient_facing_items"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id"), index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    item_type: Mapped[str] = mapped_column(String(40))
    content: Mapped[str] = mapped_column(Text)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_entry_id: Mapped[str | None] = mapped_column(ForeignKey("timeline_entries.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
