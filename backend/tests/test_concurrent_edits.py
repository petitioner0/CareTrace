from __future__ import annotations

from app.models import EntrySection, TimelineEntry
from app.services import snapshot_entry


def _collaborative_entry(db):
    entry = TimelineEntry(
        id="entry-concurrent",
        clinic_id="clinic-demo",
        patient_id="patient-amina",
        author_id="user-staff",
        author_role="staff",
        entry_type="collaborative_note",
        title="Shared care note",
    )
    db.add(entry)
    db.flush()
    db.add_all(
        [
            EntrySection(entry_id=entry.id, section_key="staff_note", content="Staff v1", updated_by="user-staff"),
            EntrySection(entry_id=entry.id, section_key="clinician_note", content="Clinician v1", updated_by="user-clinician"),
        ]
    )
    db.flush()
    snapshot_entry(db, entry, None, "user-staff")
    db.commit()
    return entry


def test_different_sections_do_not_overwrite_each_other(client, auth, db):
    entry = _collaborative_entry(db)
    staff = client.patch(
        f"/api/entries/{entry.id}/sections/staff_note",
        headers=auth("staff"),
        json={"content": "Staff v2", "base_version": 1},
    )
    clinician = client.patch(
        f"/api/entries/{entry.id}/sections/clinician_note",
        headers=auth("clinician"),
        json={"content": "Clinician v2", "base_version": 1},
    )
    assert staff.status_code == 200
    assert clinician.status_code == 200
    timeline = client.get("/api/patients/patient-amina/timeline", headers=auth("clinician")).json()
    current = next(item for item in timeline if item["id"] == entry.id)
    assert {section["content"] for section in current["sections"]} == {"Staff v2", "Clinician v2"}


def test_same_section_conflict_returns_409_deterministically(client, auth, db):
    entry = _collaborative_entry(db)
    first = client.patch(
        f"/api/entries/{entry.id}/sections/staff_note",
        headers=auth("staff"),
        json={"content": "First writer", "base_version": 1},
    )
    stale = client.patch(
        f"/api/entries/{entry.id}/sections/staff_note",
        headers=auth("staff"),
        json={"content": "Stale writer", "base_version": 1},
    )
    assert first.status_code == 200
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "section_version_conflict"
    assert stale.json()["detail"]["current_content"] == "First writer"

