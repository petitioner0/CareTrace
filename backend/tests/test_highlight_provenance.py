from __future__ import annotations

import json

from app.ai import FixtureProvider
from app.models import EntrySection, EntryVersion, Highlight, Interaction, ProcessingJob, ProvenanceEdge, TimelineEntry
from app.provenance import match_quote
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


def test_quote_matching_is_backend_owned_and_ambiguous_quotes_abstain():
    assert match_quote("Alpha beta gamma", "beta").start == 6
    assert match_quote("Alpha   beta", "Alpha beta").support == "supported"
    assert match_quote("same and same", "same") is None
    assert match_quote("source", "paraphrase") is None


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
