from __future__ import annotations

import difflib
import json
import math
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .ai import EmbeddingProvider, LLMProvider, get_provider
from .config import settings
from .models import (
    AuditEvent,
    ClinicalFact,
    CommentThread,
    Conflict,
    EmbeddingRecord,
    EntrySection,
    EntryVersion,
    FeedbackEvent,
    GlanceSnapshot,
    Highlight,
    Interaction,
    Patient,
    PreferenceProfile,
    ProcessingJob,
    ProvenanceEdge,
    TimelineEntry,
    User,
    now,
    uid,
)
from .provenance import match_quotes, quote_digest
from .redaction import assert_no_known_phi, redact
from .security import Principal, cipher


SECTION_OWNERS = {
    "staff_note": {"staff"},
    "clinician_note": {"clinician"},
    "plan": {"clinician"},
    "patient_input": {"patient"},
    "admin_note": {"admin"},
}

POSITIVE_WEIGHTS = {
    "accept": 1.0,
    "pin": 2.0,
    "highlight": 2.0,
    "comment": 0.5,
    "edit": 1.5,
    "confirm_warning": 2.0,
}


def ensure_patient_scope(db: Session, patient_id: str, principal: Principal) -> Patient:
    patient = db.scalar(select(Patient).where(Patient.id == patient_id, Patient.clinic_id == principal.clinic_id))
    if not patient or (principal.role == "patient" and principal.patient_id != patient.id):
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


def audit(db: Session, principal: Principal | None, action: str, resource_type: str, resource_id: str, **metadata) -> None:
    db.add(
        AuditEvent(
            clinic_id=principal.clinic_id if principal else metadata.pop("clinic_id"),
            actor_id=principal.id if principal else None,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata_json=json.dumps(metadata, separators=(",", ":")),
        )
    )


def _sections(db: Session, entry_id: str) -> list[EntrySection]:
    return list(db.scalars(select(EntrySection).where(EntrySection.entry_id == entry_id).order_by(EntrySection.section_key)))


def snapshot_entry(db: Session, entry: TimelineEntry, changed_section: str | None, actor_id: str | None) -> EntryVersion:
    snapshot = {
        section.section_key: {
            "content": section.content,
            "version": section.version,
            "visibility": section.visibility,
        }
        for section in _sections(db, entry.id)
    }
    version = EntryVersion(
        entry_id=entry.id,
        version=entry.current_version,
        snapshot_json=json.dumps(snapshot, ensure_ascii=False),
        changed_section=changed_section,
        changed_by=actor_id,
    )
    db.add(version)
    db.flush()
    return version


def create_manual_entry(db: Session, patient: Patient, principal: Principal, title: str, content: str) -> TimelineEntry:
    allowed_section = {
        "staff": "staff_note",
        "clinician": "clinician_note",
        "admin": "admin_note",
        "patient": "patient_input",
    }[principal.role]
    entry = TimelineEntry(
        clinic_id=principal.clinic_id,
        patient_id=patient.id,
        author_id=principal.id,
        author_role=principal.role,
        entry_type=f"{principal.role}_manual_note",
        title=title,
    )
    db.add(entry)
    db.flush()
    db.add(EntrySection(entry_id=entry.id, section_key=allowed_section, content=content, updated_by=principal.id))
    db.flush()
    snapshot_entry(db, entry, allowed_section, principal.id)
    audit(db, principal, "entry.created", "timeline_entry", entry.id, section=allowed_section)
    db.commit()
    rebuild_glance(db, patient.id)
    return entry


def update_section(
    db: Session,
    entry: TimelineEntry,
    section: EntrySection,
    principal: Principal,
    content: str,
    base_version: int,
) -> EntrySection:
    if principal.role not in SECTION_OWNERS.get(section.section_key, set()):
        raise HTTPException(status_code=403, detail="This role cannot edit the requested section")
    if section.version != base_version:
        raise HTTPException(
            status_code=409,
            detail={"code": "section_version_conflict", "current_version": section.version, "current_content": section.content},
        )
    section.content = content
    section.version += 1
    section.updated_by = principal.id
    entry.current_version += 1
    entry.updated_at = now()
    db.flush()
    snapshot_entry(db, entry, section.section_key, principal.id)
    audit(
        db,
        principal,
        "section.updated",
        "timeline_entry",
        entry.id,
        section=section.section_key,
        section_version=section.version,
        entry_version=entry.current_version,
    )
    db.commit()
    return section


def revert_section(
    db: Session,
    entry: TimelineEntry,
    principal: Principal,
    version_number: int,
    section_key: str,
) -> EntrySection:
    if principal.role not in SECTION_OWNERS.get(section_key, set()):
        raise HTTPException(status_code=403, detail="This role cannot revert the requested section")
    version = db.scalar(
        select(EntryVersion).where(EntryVersion.entry_id == entry.id, EntryVersion.version == version_number)
    )
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    previous = json.loads(version.snapshot_json).get(section_key)
    section = db.scalar(
        select(EntrySection).where(EntrySection.entry_id == entry.id, EntrySection.section_key == section_key)
    )
    if not previous or not section:
        raise HTTPException(status_code=404, detail="Section did not exist in that version")
    section.content = previous["content"]
    section.version += 1
    section.updated_by = principal.id
    entry.current_version += 1
    entry.updated_at = now()
    db.flush()
    snapshot_entry(db, entry, section_key, principal.id)
    audit(
        db,
        principal,
        "section.reverted",
        "timeline_entry",
        entry.id,
        section=section_key,
        restored_from=version_number,
        new_version=entry.current_version,
    )
    db.commit()
    return section


def entry_diff(db: Session, entry: TimelineEntry, from_version: int) -> dict:
    old = db.scalar(select(EntryVersion).where(EntryVersion.entry_id == entry.id, EntryVersion.version == from_version))
    current = db.scalar(
        select(EntryVersion).where(EntryVersion.entry_id == entry.id, EntryVersion.version == entry.current_version)
    )
    if not old or not current:
        raise HTTPException(status_code=404, detail="Version not found")
    old_data, current_data = json.loads(old.snapshot_json), json.loads(current.snapshot_json)
    keys = sorted(set(old_data) | set(current_data))
    changes = {}
    for key in keys:
        before = old_data.get(key, {}).get("content", "")
        after = current_data.get(key, {}).get("content", "")
        if before != after:
            changes[key] = "\n".join(
                difflib.unified_diff(before.splitlines(), after.splitlines(), fromfile=f"v{from_version}", tofile=f"v{entry.current_version}", lineterm="")
            )
    return {"from_version": from_version, "to_version": entry.current_version, "changes": changes}


def create_interaction(
    db: Session,
    patient: Patient,
    principal: Principal,
    interaction_type: str,
    content: str,
    synthetic_risk_tag: str | None,
) -> tuple[Interaction, ProcessingJob]:
    interaction = Interaction(
        clinic_id=principal.clinic_id,
        patient_id=patient.id,
        author_id=principal.id,
        author_role=principal.role,
        interaction_type=interaction_type,
        raw_content_encrypted=cipher.encrypt(content),
        synthetic_risk_tag=synthetic_risk_tag,
    )
    db.add(interaction)
    db.flush()
    raw_entry = TimelineEntry(
        clinic_id=principal.clinic_id,
        patient_id=patient.id,
        interaction_id=interaction.id,
        author_id=principal.id,
        author_role=principal.role,
        entry_type="raw_interaction",
        title=f"Raw {interaction_type.replace('_', ' ')}",
    )
    db.add(raw_entry)
    db.flush()
    db.add(EntrySection(entry_id=raw_entry.id, section_key="raw", content="Redaction pending", updated_by=principal.id))
    db.flush()
    snapshot_entry(db, raw_entry, "raw", principal.id)
    job = ProcessingJob(interaction_id=interaction.id)
    db.add(job)
    audit(db, principal, "interaction.created", "interaction", interaction.id, interaction_type=interaction_type)
    db.commit()
    return interaction, job


def _risk_for_candidate(interaction: Interaction, entity_type: str) -> tuple[float, str | None, str]:
    if interaction.synthetic_risk_tag:
        floor = {"low": 20.0, "high": 75.0, "critical": 90.0}[interaction.synthetic_risk_tag]
        return floor, "explicit_synthetic_risk_tag", f"Explicit synthetic risk tag: {interaction.synthetic_risk_tag}"
    if entity_type == "critical_action":
        return 90.0, "critical_unresolved_action", "Explicit critical unresolved action"
    return 0.0, None, "No deterministic risk floor"


def _base_score(entity_type: str, unresolved: bool, clinician_confirmed: bool) -> float:
    recency = 20.0
    unresolved_points = 20.0 if unresolved else 0.0
    entity_points = 15.0 if entity_type in {"allergy", "medication", "dosage", "task", "critical_action"} else 8.0
    confirmation = 10.0 if clinician_confirmed else 0.0
    return min(100.0, recency + unresolved_points + entity_points + confirmation)


def _detect_conflict(db: Session, fact: ClinicalFact, highlight: Highlight) -> None:
    if fact.entity_type not in {"allergy", "dosage"}:
        return
    previous = db.scalar(
        select(ClinicalFact)
        .where(
            ClinicalFact.patient_id == fact.patient_id,
            ClinicalFact.entity_type == fact.entity_type,
            ClinicalFact.status == "active",
            ClinicalFact.id != fact.id,
            ClinicalFact.normalized_value != fact.normalized_value,
        )
        .order_by(ClinicalFact.created_at.desc())
    )
    if not previous:
        return
    duplicate = db.scalar(
        select(Conflict).where(
            Conflict.patient_id == fact.patient_id,
            Conflict.entity_type == fact.entity_type,
            Conflict.status == "open",
            Conflict.fact_a_id == previous.id,
            Conflict.fact_b_id == fact.id,
        )
    )
    if duplicate:
        return
    db.add(
        Conflict(
            clinic_id=fact.clinic_id,
            patient_id=fact.patient_id,
            entity_type=fact.entity_type,
            fact_a_id=previous.id,
            fact_b_id=fact.id,
        )
    )
    source = f"{fact.entity_type}_conflict"
    highlight.risk_floor = max(highlight.risk_floor, 75.0)
    highlight.risk_source = source
    highlight.risk_reason = f"Unresolved {fact.entity_type} conflict"
    prior_highlight = db.scalar(select(Highlight).where(Highlight.provenance_edge_id == previous.provenance_edge_id))
    if prior_highlight:
        prior_highlight.risk_floor = max(prior_highlight.risk_floor, 75.0)
        prior_highlight.risk_source = source
        prior_highlight.risk_reason = f"Unresolved {fact.entity_type} conflict"


def process_job(job_id: str, session_factory, provider: LLMProvider & EmbeddingProvider | None = None) -> None:
    db: Session = session_factory()
    try:
        job = db.get(ProcessingJob, job_id)
        if not job:
            return
        job.status = "processing"
        job.attempts += 1
        job.error_code = None
        db.commit()
        interaction = db.get(Interaction, job.interaction_id)
        patient = db.get(Patient, interaction.patient_id)
        raw_entry = db.scalar(select(TimelineEntry).where(TimelineEntry.interaction_id == interaction.id, TimelineEntry.entry_type == "raw_interaction"))
        raw_section = db.scalar(select(EntrySection).where(EntrySection.entry_id == raw_entry.id, EntrySection.section_key == "raw"))

        original = cipher.decrypt(interaction.raw_content_encrypted)
        patient_name = cipher.decrypt(patient.name_encrypted)
        result = redact(original, [patient_name])
        assert_no_known_phi(result.redacted_text, [patient_name])
        interaction.redacted_content = result.redacted_text
        interaction.redaction_map_encrypted = cipher.encrypt(result.to_json())
        raw_section.content = result.redacted_text
        raw_section.version += 1
        raw_entry.current_version += 1
        db.flush()
        raw_version = snapshot_entry(db, raw_entry, "raw", None)

        active_provider = provider or get_provider()
        candidates = active_provider.extract({raw_entry.id: result.redacted_text})
        summary_entry = TimelineEntry(
            clinic_id=interaction.clinic_id,
            patient_id=interaction.patient_id,
            interaction_id=interaction.id,
            author_role="system",
            entry_type={
                "doctor_consult": "ai_doctor_consult_summary",
                "nurse_consult": "ai_nurse_consult_summary",
                "ai_patient_session": "ai_patient_session_summary",
            }[interaction.interaction_type],
            title="AI-scribed source-supported summary",
        )
        db.add(summary_entry)
        db.flush()
        supported_lines: list[str] = []
        boundary_map = json.loads(result.to_json())["boundary_map"]

        for candidate in candidates.facts:
            if candidate.source_ref != raw_entry.id:
                continue
            quote_matches = match_quotes(result.redacted_text, candidate.evidence_quote)
            if not quote_matches:
                continue
            primary_match = quote_matches[0]
            matched_quote = result.redacted_text[primary_match.start : primary_match.end]
            fact_id, highlight_id = uid(), uid()
            edges = []
            for quote_match in quote_matches:
                quote = result.redacted_text[quote_match.start : quote_match.end]
                edge = ProvenanceEdge(
                    target_type="clinical_fact",
                    target_id=fact_id,
                    source_entry_id=raw_entry.id,
                    source_entry_version_id=raw_version.id,
                    source_section_key="raw",
                    start_offset=quote_match.start,
                    end_offset=quote_match.end,
                    original_start_offset=boundary_map[quote_match.start],
                    original_end_offset=boundary_map[quote_match.end],
                    quote_hash=quote_digest(quote),
                    match_method=quote_match.method,
                    source_support=quote_match.support,
                )
                db.add(edge)
                edges.append(edge)
            db.flush()
            primary_edge = edges[0]
            fact = ClinicalFact(
                id=fact_id,
                clinic_id=interaction.clinic_id,
                patient_id=interaction.patient_id,
                entry_id=summary_entry.id,
                entity_type=candidate.entity_type,
                normalized_value=candidate.normalized_value,
                evidence_quote=matched_quote,
                provenance_edge_id=primary_edge.id,
            )
            unresolved = candidate.entity_type in {"task", "critical_action"}
            risk_floor, risk_source, risk_reason = _risk_for_candidate(interaction, candidate.entity_type)
            highlight = Highlight(
                id=highlight_id,
                clinic_id=interaction.clinic_id,
                patient_id=interaction.patient_id,
                entry_id=summary_entry.id,
                text=candidate.candidate_summary,
                entity_type=candidate.entity_type,
                risk_reason=risk_reason,
                risk_source=risk_source,
                risk_floor=risk_floor,
                source_support=primary_match.support,
                provenance_edge_id=primary_edge.id,
                unresolved=unresolved,
                base_score=_base_score(candidate.entity_type, unresolved, False),
            )
            db.add_all([fact, highlight])
            db.flush()
            _detect_conflict(db, fact, highlight)
            vector = active_provider.embed([highlight.text])[0]
            db.add(
                EmbeddingRecord(
                    owner_type="highlight",
                    owner_id=highlight.id,
                    model=settings.ollama_embed_model if settings.ai_provider == "ollama" else "fixture-24d",
                    vector_json=json.dumps(vector),
                )
            )
            supported_lines.append(f"• {candidate.candidate_summary}")

        summary_content = "\n".join(supported_lines) or "No source-supported facts were extracted."
        db.add(EntrySection(entry_id=summary_entry.id, section_key="summary", content=summary_content, visibility="internal"))
        db.flush()
        snapshot_entry(db, summary_entry, "summary", None)
        summary_vector = active_provider.embed([summary_content])[0]
        db.add(
            EmbeddingRecord(
                owner_type="timeline_entry",
                owner_id=summary_entry.id,
                model=settings.ollama_embed_model if settings.ai_provider == "ollama" else "fixture-24d",
                vector_json=json.dumps(summary_vector),
            )
        )
        db.flush()
        create_longitudinal_insight(db, summary_entry, summary_content, active_provider)
        interaction.status = "complete"
        job.status = "complete"
        audit(
            db,
            None,
            "ai.processing.completed",
            "interaction",
            interaction.id,
            clinic_id=interaction.clinic_id,
            provider=settings.ai_provider,
            supported_fact_count=len(supported_lines),
        )
        db.commit()
        rebuild_glance(db, interaction.patient_id)
    except Exception as exc:
        db.rollback()
        job = db.get(ProcessingJob, job_id)
        interaction = db.get(Interaction, job.interaction_id) if job else None
        if job:
            job.status = "failed"
            job.error_code = str(exc)[:80]
        if interaction:
            interaction.status = "failed"
        db.commit()
    finally:
        db.close()


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(sum(value * value for value in right))
    return sum(a * b for a, b in zip(left, right)) / denominator if denominator else 0.0


def _is_decay_protected(db: Session, entry: TimelineEntry) -> bool:
    protected = db.scalar(
        select(Highlight.id).where(
            Highlight.entry_id == entry.id,
            (Highlight.unresolved.is_(True))
            | (Highlight.risk_floor > 0)
            | (Highlight.clinician_confirmed.is_(True)),
        )
    )
    return bool(protected)


def retrieve_context_entries(
    db: Session,
    current_entry: TimelineEntry,
    query_text: str,
    provider: EmbeddingProvider,
) -> tuple[list[TimelineEntry], dict]:
    candidates = list(
        db.scalars(
            select(TimelineEntry).where(
                TimelineEntry.patient_id == current_entry.patient_id,
                TimelineEntry.id != current_entry.id,
                TimelineEntry.entry_type.like("ai_%_summary"),
            )
        )
    )
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.data_decay_threshold_days)
    eligible = []
    for entry in candidates:
        created = entry.created_at if entry.created_at.tzinfo else entry.created_at.replace(tzinfo=timezone.utc)
        if created >= cutoff or _is_decay_protected(db, entry):
            eligible.append(entry)
    eligible.sort(key=lambda item: item.created_at, reverse=True)
    recent = eligible[: settings.recent_context_count]
    recent_ids = {entry.id for entry in recent}

    query_vector = provider.embed([query_text])[0]
    scored: list[tuple[float, TimelineEntry]] = []
    for entry in eligible:
        if entry.id in recent_ids:
            continue
        embedding = db.scalar(
            select(EmbeddingRecord).where(
                EmbeddingRecord.owner_type == "timeline_entry",
                EmbeddingRecord.owner_id == entry.id,
            )
        )
        if embedding:
            scored.append((cosine(query_vector, json.loads(embedding.vector_json)), entry))
    scored.sort(key=lambda item: item[0], reverse=True)
    semantic = [entry for _, entry in scored[: settings.rag_top_k]]
    return [*recent, *semantic], {
        "recent_count": len(recent),
        "semantic_count": len(semantic),
        "recent_limit": settings.recent_context_count,
        "rag_top_k": settings.rag_top_k,
        "decay_threshold_days": settings.data_decay_threshold_days,
    }


def create_longitudinal_insight(
    db: Session,
    current_entry: TimelineEntry,
    current_summary: str,
    provider: LLMProvider & EmbeddingProvider,
) -> TimelineEntry | None:
    context_entries, policy = retrieve_context_entries(db, current_entry, current_summary, provider)
    if not context_entries:
        return None
    sources: dict[str, str] = {current_entry.id: current_summary}
    source_meta: dict[str, tuple[TimelineEntry, EntryVersion, str]] = {}
    for entry in [current_entry, *context_entries]:
        section = db.scalar(select(EntrySection).where(EntrySection.entry_id == entry.id).order_by(EntrySection.section_key))
        version = db.scalar(
            select(EntryVersion).where(EntryVersion.entry_id == entry.id).order_by(EntryVersion.version.desc())
        )
        if section and version:
            sources[entry.id] = section.content
            source_meta[entry.id] = (entry, version, section.section_key)

    candidates = provider.extract(sources)
    matched_candidates = []
    distinct_sources: set[str] = set()
    for candidate in candidates.facts:
        source = sources.get(candidate.source_ref)
        if source is None or candidate.source_ref not in source_meta:
            continue
        matches = match_quotes(source, candidate.evidence_quote)
        for matched in matches:
            matched_candidates.append((candidate, matched, source))
            distinct_sources.add(candidate.source_ref)
    if len(distinct_sources) < 2:
        return None

    insight = TimelineEntry(
        clinic_id=current_entry.clinic_id,
        patient_id=current_entry.patient_id,
        author_role="system",
        entry_type="longitudinal_insight",
        title="Source-supported longitudinal context",
    )
    db.add(insight)
    db.flush()
    seen_lines: set[str] = set()
    lines: list[str] = []
    for candidate, matched, source in matched_candidates:
        if candidate.candidate_summary not in seen_lines:
            lines.append(f"• {candidate.candidate_summary}")
            seen_lines.add(candidate.candidate_summary)
        source_entry, source_version, section_key = source_meta[candidate.source_ref]
        quote = source[matched.start : matched.end]
        db.add(
            ProvenanceEdge(
                target_type="longitudinal_insight",
                target_id=insight.id,
                source_entry_id=source_entry.id,
                source_entry_version_id=source_version.id,
                source_section_key=section_key,
                start_offset=matched.start,
                end_offset=matched.end,
                original_start_offset=matched.start,
                original_end_offset=matched.end,
                quote_hash=quote_digest(quote),
                match_method=matched.method,
                source_support=matched.support,
            )
        )
    content = "\n".join(lines)
    db.add(EntrySection(entry_id=insight.id, section_key="insight", content=content, visibility="internal"))
    db.flush()
    snapshot_entry(db, insight, "insight", None)
    vector = provider.embed([content])[0]
    db.add(
        EmbeddingRecord(
            owner_type="timeline_entry",
            owner_id=insight.id,
            model=settings.ollama_embed_model if settings.ai_provider == "ollama" else "fixture-24d",
            vector_json=json.dumps(vector),
        )
    )
    audit(
        db,
        None,
        "longitudinal.insight.created",
        "timeline_entry",
        insight.id,
        clinic_id=insight.clinic_id,
        source_count=len(distinct_sources),
        **policy,
    )
    return insight


def _profile_bonus(db: Session, viewer_id: str | None, highlight: Highlight) -> float:
    if not viewer_id:
        return 0.0
    profile = db.scalar(select(PreferenceProfile).where(PreferenceProfile.clinician_id == viewer_id))
    embedding = db.scalar(
        select(EmbeddingRecord).where(EmbeddingRecord.owner_type == "highlight", EmbeddingRecord.owner_id == highlight.id)
    )
    if not profile or not embedding:
        return 0.0
    vector = json.loads(embedding.vector_json)
    positive = json.loads(profile.positive_vector_json)
    negative = json.loads(profile.negative_vector_json)
    return max(-8.0, min(8.0, 8.0 * (cosine(vector, positive) - cosine(vector, negative))))


def rebuild_glance(db: Session, patient_id: str, viewer_id: str | None = None) -> None:
    viewer_ids: list[str | None]
    if viewer_id is not None:
        viewer_ids = [viewer_id]
    else:
        patient = db.get(Patient, patient_id)
        profile_users = list(
            db.scalars(select(User.id).where(User.clinic_id == patient.clinic_id, User.role.in_(["clinician", "staff"])))
        )
        viewer_ids = [None, *profile_users]
    highlights = list(db.scalars(select(Highlight).where(Highlight.patient_id == patient_id)))
    for current_viewer in viewer_ids:
        if current_viewer is None:
            db.execute(delete(GlanceSnapshot).where(GlanceSnapshot.patient_id == patient_id, GlanceSnapshot.viewer_id.is_(None)))
        else:
            db.execute(delete(GlanceSnapshot).where(GlanceSnapshot.patient_id == patient_id, GlanceSnapshot.viewer_id == current_viewer))
        rejected_ids: set[str] = set()
        pinned_ids: set[str] = set()
        if current_viewer:
            feedback = list(db.scalars(select(FeedbackEvent).where(FeedbackEvent.actor_id == current_viewer)))
            latest: dict[str, str] = {}
            for event in feedback:
                latest[event.highlight_id] = event.action
            rejected_ids = {key for key, action in latest.items() if action == "reject"}
            pinned_ids = {key for key, action in latest.items() if action == "pin"}
        items = []
        for highlight in highlights:
            if highlight.id in rejected_ids and highlight.risk_floor < 90:
                continue
            learned_bonus = _profile_bonus(db, current_viewer, highlight)
            final_score = max(highlight.risk_floor, min(100.0, highlight.base_score + learned_bonus))
            primary_edge = db.get(ProvenanceEdge, highlight.provenance_edge_id)
            provenance_ids = [highlight.provenance_edge_id]
            if primary_edge:
                provenance_ids = list(
                    db.scalars(
                        select(ProvenanceEdge.id).where(
                            ProvenanceEdge.target_type == primary_edge.target_type,
                            ProvenanceEdge.target_id == primary_edge.target_id,
                        )
                    )
                )
                provenance_ids.sort(key=lambda edge_id: edge_id != highlight.provenance_edge_id)
            items.append(
                {
                    "id": highlight.id,
                    "entry_id": highlight.entry_id,
                    "text": highlight.text,
                    "entity_type": highlight.entity_type,
                    "risk_reason": highlight.risk_reason,
                    "risk_source": highlight.risk_source,
                    "risk_floor": round(highlight.risk_floor, 1),
                    "source_support": highlight.source_support,
                    "provenance_id": highlight.provenance_edge_id,
                    "provenance_ids": provenance_ids,
                    "source_count": len(provenance_ids),
                    "multiple_sources": len(provenance_ids) > 1,
                    "unresolved": highlight.unresolved,
                    "status": highlight.status,
                    "pinned": highlight.id in pinned_ids or highlight.pinned,
                    "score": round(final_score, 1),
                    "score_breakdown": {
                        "rule_score": round(highlight.base_score, 1),
                        "learned_bonus": round(learned_bonus, 1),
                        "risk_floor": round(highlight.risk_floor, 1),
                    },
                }
            )
        items.sort(key=lambda item: (item["pinned"], item["score"], item["unresolved"]), reverse=True)
        db.add(
            GlanceSnapshot(
                patient_id=patient_id,
                viewer_id=current_viewer,
                items_json=json.dumps(items[: settings.glance_max_items]),
                generated_at=datetime.now(timezone.utc),
            )
        )
    db.commit()


def _weighted_centroid(current: list[float], current_weight: float, new: list[float], weight: float) -> list[float]:
    if not current or current_weight <= 0:
        return new
    total = current_weight + weight
    combined = [(a * current_weight + b * weight) / total for a, b in zip(current, new)]
    norm = math.sqrt(sum(value * value for value in combined)) or 1.0
    return [value / norm for value in combined]


def apply_feedback(
    db: Session,
    principal: Principal,
    highlight: Highlight,
    action: str,
    provider: EmbeddingProvider | None = None,
) -> FeedbackEvent:
    if principal.role not in {"staff", "clinician"}:
        raise HTTPException(status_code=403, detail="Only care-team users can provide ranking feedback")
    if action == "confirm_warning" and principal.role != "clinician":
        raise HTTPException(status_code=403, detail="Only clinicians can confirm a warning")
    profile = db.scalar(select(PreferenceProfile).where(PreferenceProfile.clinician_id == principal.id))
    if not profile:
        profile = PreferenceProfile(clinician_id=principal.id)
        db.add(profile)
        db.flush()
    embedding = db.scalar(
        select(EmbeddingRecord).where(EmbeddingRecord.owner_type == "highlight", EmbeddingRecord.owner_id == highlight.id)
    )
    if embedding:
        vector = json.loads(embedding.vector_json)
    else:
        active_provider = provider or get_provider()
        vector = active_provider.embed([highlight.text])[0]
        db.add(EmbeddingRecord(owner_type="highlight", owner_id=highlight.id, model="feedback", vector_json=json.dumps(vector)))
    if action == "reject":
        current = json.loads(profile.negative_vector_json)
        profile.negative_vector_json = json.dumps(_weighted_centroid(current, profile.negative_weight, vector, 1.0))
        profile.negative_weight += 1.0
    else:
        weight = POSITIVE_WEIGHTS[action]
        current = json.loads(profile.positive_vector_json)
        profile.positive_vector_json = json.dumps(_weighted_centroid(current, profile.positive_weight, vector, weight))
        profile.positive_weight += weight
    profile.version += 1
    if action == "pin":
        highlight.pinned = True
    if action == "accept":
        highlight.status = "accepted"
    if action == "confirm_warning":
        highlight.clinician_confirmed = True
        highlight.risk_floor = max(highlight.risk_floor, 90.0)
        highlight.risk_source = "clinician_confirmed_warning"
        highlight.risk_reason = "Clinician-confirmed warning"
    event = FeedbackEvent(
        highlight_id=highlight.id,
        actor_id=principal.id,
        action=action,
        profile_version=profile.version,
        impression_seen=True,
    )
    db.add(event)
    audit(db, principal, "highlight.feedback", "highlight", highlight.id, feedback_action=action, profile_version=profile.version)
    db.commit()
    rebuild_glance(db, highlight.patient_id)
    return event


def serialize_entry(db: Session, entry: TimelineEntry, include_comments: bool = True) -> dict:
    sections = _sections(db, entry.id)
    comments = []
    if include_comments:
        comments = list(db.scalars(select(CommentThread).where(CommentThread.entry_id == entry.id).order_by(CommentThread.created_at)))
    return {
        "id": entry.id,
        "patient_id": entry.patient_id,
        "author_role": entry.author_role,
        "entry_type": entry.entry_type,
        "title": entry.title,
        "current_version": entry.current_version,
        "created_at": entry.created_at.isoformat(),
        "sections": [
            {
                "key": section.section_key,
                "content": section.content,
                "version": section.version,
                "visibility": section.visibility,
            }
            for section in sections
        ],
        "comments": [
            {
                "id": comment.id,
                "content": comment.content,
                "author_id": comment.author_id,
                "mention_user_id": comment.mention_user_id,
                "assigned_to_id": comment.assigned_to_id,
                "resolved": comment.resolved,
                "created_at": comment.created_at.isoformat(),
            }
            for comment in comments
        ],
    }
