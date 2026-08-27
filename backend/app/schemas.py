from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Role = Literal["patient", "staff", "clinician", "admin"]


class TokenRequest(BaseModel):
    email: str
    password: str


class InteractionCreate(BaseModel):
    interaction_type: Literal["doctor_consult", "nurse_consult", "ai_patient_session"]
    content: str = Field(min_length=1, max_length=30_000)
    synthetic_risk_tag: Literal["low", "high", "critical"] | None = None


class ManualEntryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=20_000)


class SectionUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    base_version: int = Field(ge=1)


class RevertRequest(BaseModel):
    version: int = Field(ge=1)
    section_key: str


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2_000)
    mention_user_id: str | None = None
    assigned_to_id: str | None = None


class CommentUpdate(BaseModel):
    resolved: bool


class FeedbackCreate(BaseModel):
    action: Literal["accept", "reject", "pin", "highlight", "comment", "edit", "confirm_warning"]


class ConflictResolve(BaseModel):
    winning_fact_id: str
    reason: str = Field(min_length=3, max_length=500)


class PatientFacingCreate(BaseModel):
    patient_id: str
    item_type: Literal["summary", "instruction"]
    content: str = Field(min_length=1, max_length=5_000)
    approved: bool = True
    source_entry_id: str | None = None


class CandidateFact(BaseModel):
    model_config = ConfigDict(extra="ignore")
    source_ref: str
    evidence_quote: str
    normalized_value: str
    entity_type: Literal["allergy", "medication", "dosage", "task", "clinical_entity", "critical_action"]
    candidate_summary: str
    model_uncertainty_reason: str | None = None


class CandidateBatch(BaseModel):
    model_config = ConfigDict(extra="ignore")
    facts: list[CandidateFact] = Field(default_factory=list)

