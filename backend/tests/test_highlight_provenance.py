from __future__ import annotations

import json

from app.ai import FixtureProvider
from app.models import EntrySection, EntryVersion, ExtractionOutcome, Highlight, Interaction, ProcessingJob, ProvenanceEdge, TimelineEntry
from app.provenance import match_quote, match_quotes
from app.schemas import CandidateBatch, CandidateFact
from app.security import Principal, cipher
from app.services import create_interaction, process_job


def test_seeded_highlights_resolve_to_immutable_entry_span(client, auth, db):
    headers = auth("clinician")
    items = client.get("/api/patients/patient-amina/glance", headers=headers).json()["items"]
    assert items
    for item in items:
        response = client.get(f"/api/provenance/{item['provenance_id']}", headers=headers)
        assert response.status_code == 200
        provenance = response.json()
        assert provenance["integrity"] == "verified"
        assert provenance["quote"]
        assert provenance["end_offset"] > provenance["start_offset"]
        version = db.get(EntryVersion, provenance["source_entry_version_id"])
        source = json.loads(version.snapshot_json)[provenance["section_key"]]["content"]
        assert source[provenance["start_offset"] : provenance["end_offset"]] == provenance["quote"]

    first = items[0]
    provenance_before = client.get(f"/api/provenance/{first['provenance_id']}", headers=headers).json()
    source_entry = db.get(TimelineEntry, provenance_before["source_entry_id"])
    source_section = db.query(EntrySection).filter_by(entry_id=source_entry.id, section_key="raw").one()
    source_section.content = "A later representation that does not alter the historical version."
    source_section.version += 1
    source_entry.current_version += 1
    db.add(
        EntryVersion(
            entry_id=source_entry.id,
            version=source_entry.current_version,
            snapshot_json=json.dumps({"raw": {"content": source_section.content, "version": source_section.version, "visibility": "internal"}}),
            changed_section="raw",
        )
    )
    db.commit()
    provenance_after = client.get(f"/api/provenance/{first['provenance_id']}", headers=headers).json()
    assert provenance_after["quote"] == provenance_before["quote"]
    assert provenance_after["source_entry_version_id"] == provenance_before["source_entry_version_id"]


def test_quote_matching_is_backend_owned_and_returns_every_repeated_match():
    assert match_quote("Alpha beta gamma", "beta").start == 6
    assert match_quote("Alpha   beta", "Alpha beta").support == "supported"
    matches = match_quotes("same and same", "same")
    assert [(match.start, match.end) for match in matches] == [(0, 4), (9, 13)]
    assert match_quote("source", "paraphrase") is None


def test_repeated_evidence_returns_and_labels_all_sources(client, auth, db):
    class RepeatedEvidenceProvider(FixtureProvider):
        def extract(self, sources):
            source_ref = next(iter(sources))
            return CandidateBatch(
                facts=[
                    CandidateFact(
                        source_ref=source_ref,
                        evidence_quote="Critical action: confirm the active dose.",
                        normalized_value="confirm active dose",
                        entity_type="critical_action",
                        candidate_summary="Confirm the active dose.",
                    )
                ]
            )

    patient = db.get(__import__("app.models", fromlist=["Patient"]).Patient, "patient-amina")
    principal = Principal("user-clinician", "clinic-demo", "clinician", None, "Dr. Maya Chen")
    _, job = create_interaction(
        db,
        patient,
        principal,
        "doctor_consult",
        "Critical action: confirm the active dose. Critical action: confirm the active dose.",
        None,
    )
    process_job(job.id, __import__("app.database", fromlist=["SessionLocal"]).SessionLocal, RepeatedEvidenceProvider())
    db.expire_all()
    highlight = db.query(Highlight).filter_by(text="Confirm the active dose.").one()

    response = client.get(f"/api/provenance/{highlight.provenance_edge_id}", headers=auth("clinician"))
    assert response.status_code == 200
    provenance = response.json()
    assert provenance["multiple_sources"] is True
    assert provenance["source_count"] == 2
    assert len(provenance["sources"]) == 2
    assert len({source["start_offset"] for source in provenance["sources"]}) == 2
    assert all(source["integrity"] == "verified" for source in provenance["sources"])

    items = client.get("/api/patients/patient-amina/glance", headers=auth("clinician")).json()["items"]
    item = next(item for item in items if item["id"] == highlight.id)
    assert item["multiple_sources"] is True
    assert item["source_count"] == 2
    assert len(item["provenance_ids"]) == 2


def test_longitudinal_insight_keeps_multiple_source_edges(client, db):
    insight = (
        db.query(TimelineEntry)
        .filter(TimelineEntry.patient_id == "patient-amina", TimelineEntry.entry_type == "longitudinal_insight")
        .first()
    )
    assert insight is not None
    edges = db.query(ProvenanceEdge).filter_by(target_type="longitudinal_insight", target_id=insight.id).all()
    assert len({edge.source_entry_id for edge in edges}) >= 2
    assert all(db.get(EntryVersion, edge.source_entry_version_id) for edge in edges)


def test_provider_never_receives_phi_and_offsets_from_llm_are_ignored(client, db):
    class SpyProvider(FixtureProvider):
        seen = None

        def extract(self, sources):
            self.seen = sources
            source_ref, text = next(iter(sources.items()))
            data = {
                "facts": [
                    {
                        "source_ref": source_ref,
                        "evidence_quote": "The follow-up lab order remains unresolved.",
                        "normalized_value": "lab order unresolved",
                        "entity_type": "task",
                        "candidate_summary": "Lab order remains unresolved.",
                        "start_offset": 9999,
                        "end_offset": 10020,
                    }
                ]
            }
            return CandidateBatch.model_validate(data)

    patient = db.get(__import__("app.models", fromlist=["Patient"]).Patient, "patient-amina")
    principal = Principal("user-clinician", "clinic-demo", "clinician", None, "Dr. Maya Chen")
    interaction, job = create_interaction(
        db,
        patient,
        principal,
        "doctor_consult",
        "Amina Rahman called from +65 8123 4567. The follow-up lab order remains unresolved.",
        None,
    )
    provider = SpyProvider()
    process_job(job.id, __import__("app.database", fromlist=["SessionLocal"]).SessionLocal, provider)
    combined = " ".join(provider.seen.values())
    assert "Amina Rahman" not in combined
    assert "8123 4567" not in combined
    edge = db.query(ProvenanceEdge).join(Highlight, Highlight.provenance_edge_id == ProvenanceEdge.id).filter(Highlight.patient_id == patient.id).order_by(ProvenanceEdge.id.desc()).first()
    assert edge.start_offset != 9999


def test_unmatched_candidates_are_persisted_as_review_required(client, auth, db):
    class MixedTrustProvider(FixtureProvider):
        def extract(self, sources):
            source_ref = next(iter(sources))
            return CandidateBatch(
                facts=[
                    CandidateFact(
                        source_ref=source_ref,
                        evidence_quote="The follow-up lab order remains unresolved.",
                        normalized_value="lab order unresolved",
                        entity_type="task",
                        candidate_summary="Lab order remains unresolved.",
                    ),
                    CandidateFact(
                        source_ref="unknown-source",
                        evidence_quote="The follow-up lab order remains unresolved.",
                        normalized_value="wrong source",
                        entity_type="task",
                        candidate_summary="Wrong-source candidate.",
                    ),
                    CandidateFact(
                        source_ref=source_ref,
                        evidence_quote="This quote is absent from the source.",
                        normalized_value="missing evidence",
                        entity_type="task",
                        candidate_summary="Unmatched candidate.",
                    ),
                ]
            )

    patient = db.get(__import__("app.models", fromlist=["Patient"]).Patient, "patient-amina")
    principal = Principal("user-clinician", "clinic-demo", "clinician", None, "Dr. Maya Chen")
    _, job = create_interaction(
        db,
        patient,
        principal,
        "doctor_consult",
        "The follow-up lab order remains unresolved.",
        None,
    )
    process_job(job.id, __import__("app.database", fromlist=["SessionLocal"]).SessionLocal, MixedTrustProvider())

    payload = client.get(f"/api/jobs/{job.id}", headers=auth("clinician")).json()
    assert payload["status"] == "complete"
    assert payload["trust_summary"] == {
        "verified": 1,
        "supported": 0,
        "review_required": 2,
        "abstained": 0,
    }
    assert {item["reason_code"] for item in payload["outcomes"]} == {
        "exact_match",
        "unknown_source_ref",
        "evidence_not_found",
    }
    assert all(
        item["provenance_id"] is None
        for item in payload["outcomes"]
        if item["outcome"] == "review_required"
    )
    assert db.query(ExtractionOutcome).filter_by(job_id=job.id).count() == 3
    assert db.query(Highlight).filter(Highlight.text.in_(["Wrong-source candidate.", "Unmatched candidate."])).count() == 0


def test_empty_and_malformed_provider_outputs_have_first_class_outcomes(client, auth, db):
    class EmptyProvider(FixtureProvider):
        def extract(self, sources):
            return CandidateBatch()

    class MalformedProvider(FixtureProvider):
        def extract(self, sources):
            return {"facts": [{"source_ref": "missing-required-fields"}]}

    patient = db.get(__import__("app.models", fromlist=["Patient"]).Patient, "patient-amina")
    principal = Principal("user-clinician", "clinic-demo", "clinician", None, "Dr. Maya Chen")
    cases = [
        (EmptyProvider(), "abstained", "provider_returned_no_candidates"),
        (MalformedProvider(), "review_required", "provider_output_invalid"),
    ]
    for provider, expected_outcome, expected_reason in cases:
        _, job = create_interaction(
            db,
            patient,
            principal,
            "doctor_consult",
            "No eligible structured fact in this interaction.",
            None,
        )
        process_job(job.id, __import__("app.database", fromlist=["SessionLocal"]).SessionLocal, provider)
        payload = client.get(f"/api/jobs/{job.id}", headers=auth("clinician")).json()
        assert payload["status"] == "complete"
        assert payload["trust_summary"][expected_outcome] == 1
        assert payload["outcomes"] == [
            {
                "candidate_index": None,
                "outcome": expected_outcome,
                "reason_code": expected_reason,
                "provenance_id": None,
            }
        ]


def test_redaction_policy_block_is_persisted_as_abstained(client, auth, db, monkeypatch):
    class ProviderMustNotRun(FixtureProvider):
        called = False

        def extract(self, sources):
            self.called = True
            return CandidateBatch()

    def block_provider_call(redacted_text, known_names):
        raise ValueError("redaction_review_required")

    monkeypatch.setattr("app.services.assert_no_known_phi", block_provider_call)
    patient = db.get(__import__("app.models", fromlist=["Patient"]).Patient, "patient-amina")
    principal = Principal("user-clinician", "clinic-demo", "clinician", None, "Dr. Maya Chen")
    _, job = create_interaction(
        db,
        patient,
        principal,
        "doctor_consult",
        "Amina Rahman submitted text requiring redaction review.",
        None,
    )
    provider = ProviderMustNotRun()
    process_job(job.id, __import__("app.database", fromlist=["SessionLocal"]).SessionLocal, provider)

    payload = client.get(f"/api/jobs/{job.id}", headers=auth("clinician")).json()
    assert provider.called is False
    assert payload["status"] == "complete"
    assert payload["trust_summary"]["abstained"] == 1
    assert payload["outcomes"][0]["reason_code"] == "redaction_policy_blocked"
