from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine, get_db
from .models import (
    AuditEvent,
    ClinicalFact,
    CommentThread,
    Conflict,
    EntrySection,
    EntryVersion,
    GlanceSnapshot,
    Highlight,
    Interaction,
    Patient,
    PatientFacingItem,
    ProcessingJob,
    ProvenanceEdge,
    TimelineEntry,
    User,
)
from .provenance import quote_digest
from .schemas import (
    CommentCreate,
    CommentUpdate,
    ConflictResolve,
    FeedbackCreate,
    InteractionCreate,
    ManualEntryCreate,
    PatientFacingCreate,
    RevertRequest,
    SectionUpdate,
    TokenRequest,
)
from .security import Principal, cipher, current_principal, issue_token, require_roles, verify_password
from .seed import DEMO_PASSWORD, seed_database
from .services import (
    apply_feedback,
    audit,
    create_interaction,
    create_manual_entry,
    ensure_patient_scope,
    entry_diff,
    process_job,
    rebuild_glance,
    revert_section,
    serialize_entry,
    update_section,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        seed_database(db)
        db.execute(text("PRAGMA optimize"))
        db.commit()
    finally:
        db.close()
    yield


app = FastAPI(
    title="CareTrace API",
    version="0.1.0",
    description="Trust-centered longitudinal care note prototype. Synthetic data only; not clinical decision support.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/demo/accounts")
def demo_accounts() -> dict:
    return {
        "password": DEMO_PASSWORD,
        "accounts": [
            {"role": role, "email": f"{role}@caretrace.demo"}
            for role in ("clinician", "staff", "patient", "admin")
        ],
    }


@app.post("/api/auth/token")
def login(payload: TokenRequest, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {
        "access_token": issue_token(user),
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "display_name": user.display_name,
            "role": user.role,
            "clinic_id": user.clinic_id,
            "patient_id": user.patient_id,
        },
    }


@app.get("/api/patients")
def list_patients(principal: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    query = select(Patient).where(Patient.clinic_id == principal.clinic_id).order_by(Patient.display_code)
    if principal.role == "patient":
        query = query.where(Patient.id == principal.patient_id)
    return [
        {"id": patient.id, "display_code": patient.display_code, "name": cipher.decrypt(patient.name_encrypted)}
        for patient in db.scalars(query)
    ]


@app.get("/api/patients/{patient_id}/glance")
def get_glance(
    patient_id: str,
    principal: Principal = Depends(require_roles("staff", "clinician", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    ensure_patient_scope(db, patient_id, principal)
    viewer_id = principal.id if principal.role in {"staff", "clinician"} else None
    snapshot = db.scalar(
        select(GlanceSnapshot).where(GlanceSnapshot.patient_id == patient_id, GlanceSnapshot.viewer_id == viewer_id)
    )
    if not snapshot:
        rebuild_glance(db, patient_id, viewer_id)
        snapshot = db.scalar(
            select(GlanceSnapshot).where(GlanceSnapshot.patient_id == patient_id, GlanceSnapshot.viewer_id == viewer_id)
        )
    items = json.loads(snapshot.items_json) if snapshot else []
    return {
        "patient_id": patient_id,
        "generated_at": snapshot.generated_at.isoformat() if snapshot else None,
        "items": items,
        "open_actions": [item for item in items if item["unresolved"]],
        "policy_notice": "Priority support only. CareTrace does not diagnose or infer clinical danger from symptoms.",
    }


@app.get("/api/patients/{patient_id}/timeline")
def get_timeline(
    patient_id: str,
    principal: Principal = Depends(require_roles("staff", "clinician", "admin")),
    db: Session = Depends(get_db),
) -> list[dict]:
    ensure_patient_scope(db, patient_id, principal)
    entries = db.scalars(
        select(TimelineEntry).where(TimelineEntry.patient_id == patient_id).order_by(TimelineEntry.created_at.desc())
    )
    return [serialize_entry(db, entry) for entry in entries]


@app.post("/api/patients/{patient_id}/entries", status_code=201)
def add_manual_entry(
    patient_id: str,
    payload: ManualEntryCreate,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> dict:
    patient = ensure_patient_scope(db, patient_id, principal)
    entry = create_manual_entry(db, patient, principal, payload.title, payload.content)
    return serialize_entry(db, entry)


@app.post("/api/patients/{patient_id}/interactions", status_code=status.HTTP_202_ACCEPTED)
def add_interaction(
    patient_id: str,
    payload: InteractionCreate,
    background_tasks: BackgroundTasks,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> dict:
    patient = ensure_patient_scope(db, patient_id, principal)
    expected_roles = {
        "doctor_consult": {"clinician"},
        "nurse_consult": {"staff"},
        "ai_patient_session": {"patient"},
    }
    if principal.role not in expected_roles[payload.interaction_type]:
        raise HTTPException(status_code=403, detail="Role does not match interaction type")
    interaction, job = create_interaction(
        db, patient, principal, payload.interaction_type, payload.content, payload.synthetic_risk_tag
    )
    background_tasks.add_task(process_job, job.id, SessionLocal)
    return {"interaction_id": interaction.id, "job_id": job.id, "status": job.status}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    job = db.get(ProcessingJob, job_id)
    interaction = db.get(Interaction, job.interaction_id) if job else None
    if not job or not interaction or interaction.clinic_id != principal.clinic_id:
        raise HTTPException(status_code=404, detail="Job not found")
    if principal.role == "patient" and interaction.patient_id != principal.patient_id:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"id": job.id, "interaction_id": job.interaction_id, "status": job.status, "attempts": job.attempts, "error_code": job.error_code}


@app.post("/api/jobs/{job_id}/retry", status_code=202)
def retry_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> dict:
    job = db.get(ProcessingJob, job_id)
    interaction = db.get(Interaction, job.interaction_id) if job else None
    if not job or not interaction or interaction.clinic_id != principal.clinic_id:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in {"failed", "pending"}:
        raise HTTPException(status_code=409, detail="Only failed or pending jobs can be retried")
    job.status = "pending"
    db.commit()
    background_tasks.add_task(process_job, job.id, SessionLocal)
    return {"id": job.id, "status": "pending"}


def _entry_in_scope(db: Session, entry_id: str, principal: Principal) -> TimelineEntry:
    entry = db.scalar(
        select(TimelineEntry).where(TimelineEntry.id == entry_id, TimelineEntry.clinic_id == principal.clinic_id)
    )
    if not entry or (principal.role == "patient" and entry.patient_id != principal.patient_id):
        raise HTTPException(status_code=404, detail="Entry not found")
    return entry


@app.patch("/api/entries/{entry_id}/sections/{section_key}")
def edit_section(
    entry_id: str,
    section_key: str,
    payload: SectionUpdate,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> dict:
    entry = _entry_in_scope(db, entry_id, principal)
    section = db.scalar(
        select(EntrySection).where(EntrySection.entry_id == entry.id, EntrySection.section_key == section_key)
    )
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    updated = update_section(db, entry, section, principal, payload.content, payload.base_version)
    return {"entry_id": entry.id, "section": section_key, "version": updated.version, "entry_version": entry.current_version}


@app.get("/api/entries/{entry_id}/versions")
def list_versions(
    entry_id: str,
    principal: Principal = Depends(require_roles("staff", "clinician", "admin")),
    db: Session = Depends(get_db),
) -> list[dict]:
    _entry_in_scope(db, entry_id, principal)
    versions = db.scalars(select(EntryVersion).where(EntryVersion.entry_id == entry_id).order_by(EntryVersion.version.desc()))
    return [
        {
            "id": version.id,
            "version": version.version,
            "changed_section": version.changed_section,
            "changed_by": version.changed_by,
            "created_at": version.created_at.isoformat(),
        }
        for version in versions
    ]


@app.get("/api/entries/{entry_id}/diff")
def get_diff(
    entry_id: str,
    from_version: int = Query(ge=1),
    principal: Principal = Depends(require_roles("staff", "clinician", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    entry = _entry_in_scope(db, entry_id, principal)
    return entry_diff(db, entry, from_version)


@app.post("/api/entries/{entry_id}/revert")
def revert(
    entry_id: str,
    payload: RevertRequest,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> dict:
    entry = _entry_in_scope(db, entry_id, principal)
    section = revert_section(db, entry, principal, payload.version, payload.section_key)
    return {"entry_id": entry.id, "section": section.section_key, "version": section.version, "entry_version": entry.current_version}


@app.post("/api/entries/{entry_id}/comments", status_code=201)
def add_comment(
    entry_id: str,
    payload: CommentCreate,
    principal: Principal = Depends(require_roles("staff", "clinician", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    entry = _entry_in_scope(db, entry_id, principal)
    for user_id in (payload.mention_user_id, payload.assigned_to_id):
        if user_id and not db.scalar(select(User).where(User.id == user_id, User.clinic_id == principal.clinic_id)):
            raise HTTPException(status_code=400, detail="Mention or assignee is outside the clinic")
    comment = CommentThread(
        clinic_id=principal.clinic_id,
        entry_id=entry.id,
        author_id=principal.id,
        content=payload.content,
        mention_user_id=payload.mention_user_id,
        assigned_to_id=payload.assigned_to_id,
    )
    db.add(comment)
    audit(db, principal, "comment.created", "timeline_entry", entry.id, comment_id=comment.id)
    db.commit()
    return {"id": comment.id, "resolved": comment.resolved}


@app.patch("/api/comments/{comment_id}")
def update_comment(
    comment_id: str,
    payload: CommentUpdate,
    principal: Principal = Depends(require_roles("staff", "clinician", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    comment = db.scalar(select(CommentThread).where(CommentThread.id == comment_id, CommentThread.clinic_id == principal.clinic_id))
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    comment.resolved = payload.resolved
    audit(db, principal, "comment.resolution_changed", "comment", comment.id, resolved=payload.resolved)
    db.commit()
    return {"id": comment.id, "resolved": comment.resolved}


@app.get("/api/provenance/{edge_id}")
def get_provenance(
    edge_id: str,
    principal: Principal = Depends(require_roles("staff", "clinician", "admin")),
    db: Session = Depends(get_db),
) -> dict:
    edge = db.get(ProvenanceEdge, edge_id)
    entry = db.get(TimelineEntry, edge.source_entry_id) if edge else None
    version = db.get(EntryVersion, edge.source_entry_version_id) if edge else None
    if not edge or not entry or not version or entry.clinic_id != principal.clinic_id:
        raise HTTPException(status_code=404, detail="Provenance not found")
    snapshot = json.loads(version.snapshot_json)
    source = snapshot.get(edge.source_section_key, {}).get("content", "")
    quote = source[edge.start_offset : edge.end_offset]
    if quote_digest(quote) != edge.quote_hash:
        raise HTTPException(status_code=409, detail="Stored provenance failed integrity validation")
    original_quote = None
    if entry.interaction_id:
        interaction = db.get(Interaction, entry.interaction_id)
        original = cipher.decrypt(interaction.raw_content_encrypted)
        original_quote = original[edge.original_start_offset : edge.original_end_offset]
    return {
        "id": edge.id,
        "source_entry_id": entry.id,
        "source_entry_version_id": version.id,
        "entry_version": version.version,
        "section_key": edge.source_section_key,
        "start_offset": edge.start_offset,
        "end_offset": edge.end_offset,
        "quote": quote,
        "original_quote": original_quote,
        "original_start_offset": edge.original_start_offset,
        "original_end_offset": edge.original_end_offset,
        "match_method": edge.match_method,
        "source_support": edge.source_support,
        "integrity": "verified",
    }


@app.post("/api/highlights/{highlight_id}/feedback")
def highlight_feedback(
    highlight_id: str,
    payload: FeedbackCreate,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> dict:
    highlight = db.scalar(
        select(Highlight).where(Highlight.id == highlight_id, Highlight.clinic_id == principal.clinic_id)
    )
    if not highlight:
        raise HTTPException(status_code=404, detail="Highlight not found")
    event = apply_feedback(db, principal, highlight, payload.action)
    return {"event_id": event.id, "profile_version": event.profile_version, "action": event.action}


@app.get("/api/conflicts")
def list_conflicts(
    patient_id: str | None = None,
    principal: Principal = Depends(require_roles("staff", "clinician", "admin")),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(Conflict).where(Conflict.clinic_id == principal.clinic_id)
    if patient_id:
        ensure_patient_scope(db, patient_id, principal)
        query = query.where(Conflict.patient_id == patient_id)
    conflicts = db.scalars(query.order_by(Conflict.created_at.desc()))
    result = []
    for conflict in conflicts:
        fact_a, fact_b = db.get(ClinicalFact, conflict.fact_a_id), db.get(ClinicalFact, conflict.fact_b_id)
        result.append(
            {
                "id": conflict.id,
                "patient_id": conflict.patient_id,
                "entity_type": conflict.entity_type,
                "status": conflict.status,
                "fact_a": {"id": fact_a.id, "value": fact_a.normalized_value, "quote": fact_a.evidence_quote},
                "fact_b": {"id": fact_b.id, "value": fact_b.normalized_value, "quote": fact_b.evidence_quote},
            }
        )
    return result


@app.post("/api/conflicts/{conflict_id}/resolve")
def resolve_conflict(
    conflict_id: str,
    payload: ConflictResolve,
    principal: Principal = Depends(require_roles("clinician")),
    db: Session = Depends(get_db),
) -> dict:
    conflict = db.scalar(select(Conflict).where(Conflict.id == conflict_id, Conflict.clinic_id == principal.clinic_id))
    if not conflict:
        raise HTTPException(status_code=404, detail="Conflict not found")
    if payload.winning_fact_id not in {conflict.fact_a_id, conflict.fact_b_id}:
        raise HTTPException(status_code=400, detail="Winning fact must belong to this conflict")
    winner = db.get(ClinicalFact, payload.winning_fact_id)
    loser = db.get(ClinicalFact, conflict.fact_b_id if winner.id == conflict.fact_a_id else conflict.fact_a_id)
    winner.clinician_confirmed = True
    loser.status = "superseded"
    for fact in (winner, loser):
        linked_highlight = db.scalar(select(Highlight).where(Highlight.provenance_edge_id == fact.provenance_edge_id))
        if linked_highlight and linked_highlight.risk_source == f"{conflict.entity_type}_conflict":
            linked_highlight.risk_floor = 0
            linked_highlight.risk_source = None
            linked_highlight.risk_reason = "Conflict resolved by clinician"
        if linked_highlight and fact.id == winner.id:
            linked_highlight.clinician_confirmed = True
            linked_highlight.base_score = min(100, linked_highlight.base_score + 10)
    conflict.status = "resolved"
    conflict.resolution_fact_id = winner.id
    conflict.resolved_by = principal.id
    audit(db, principal, "conflict.resolved", "conflict", conflict.id, winning_fact_id=winner.id, reason=payload.reason)
    db.commit()
    rebuild_glance(db, conflict.patient_id)
    return {"id": conflict.id, "status": conflict.status, "winning_fact_id": winner.id}


@app.get("/api/patient-facing-items")
def patient_facing_items(
    patient_id: str | None = None,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> list[dict]:
    target_patient = principal.patient_id if principal.role == "patient" else patient_id
    if not target_patient:
        raise HTTPException(status_code=400, detail="patient_id is required")
    ensure_patient_scope(db, target_patient, principal)
    query = select(PatientFacingItem).where(
        PatientFacingItem.patient_id == target_patient,
        PatientFacingItem.clinic_id == principal.clinic_id,
    )
    if principal.role == "patient":
        query = query.where(PatientFacingItem.approved.is_(True))
    return [
        {
            "id": item.id,
            "item_type": item.item_type,
            "content": item.content,
            "approved": item.approved,
            "approved_by": item.approved_by,
            "approved_at": item.approved_at.isoformat() if item.approved_at else None,
        }
        for item in db.scalars(query.order_by(PatientFacingItem.created_at.desc()))
    ]


@app.post("/api/patient-facing-items", status_code=201)
def create_patient_facing_item(
    payload: PatientFacingCreate,
    principal: Principal = Depends(require_roles("clinician")),
    db: Session = Depends(get_db),
) -> dict:
    ensure_patient_scope(db, payload.patient_id, principal)
    if payload.source_entry_id:
        _entry_in_scope(db, payload.source_entry_id, principal)
    item = PatientFacingItem(
        clinic_id=principal.clinic_id,
        patient_id=payload.patient_id,
        item_type=payload.item_type,
        content=payload.content,
        approved=payload.approved,
        approved_by=principal.id if payload.approved else None,
        approved_at=datetime.now(timezone.utc) if payload.approved else None,
        source_entry_id=payload.source_entry_id,
    )
    db.add(item)
    audit(db, principal, "patient_facing_item.created", "patient_facing_item", item.id, approved=item.approved)
    db.commit()
    return {"id": item.id, "approved": item.approved}


@app.get("/api/audit")
def audit_log(
    resource_id: str | None = None,
    principal: Principal = Depends(require_roles("clinician", "admin")),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(AuditEvent).where(AuditEvent.clinic_id == principal.clinic_id)
    if resource_id:
        query = query.where(AuditEvent.resource_id == resource_id)
    return [
        {
            "id": event.id,
            "actor_id": event.actor_id,
            "action": event.action,
            "resource_type": event.resource_type,
            "resource_id": event.resource_id,
            "metadata": json.loads(event.metadata_json),
            "created_at": event.created_at.isoformat(),
        }
        for event in db.scalars(query.order_by(AuditEvent.created_at.desc()).limit(200))
    ]
