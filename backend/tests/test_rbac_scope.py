from __future__ import annotations

from app.models import Clinic, Patient
from app.security import cipher


def test_staff_and_clinician_cannot_edit_each_others_sections(client, auth):
    staff_headers = auth("staff")
    clinician_headers = auth("clinician")
    staff_entry = client.post(
        "/api/patients/patient-amina/entries",
        headers=staff_headers,
        json={"title": "Staff follow-up", "content": "Waiting for records."},
    ).json()
    response = client.patch(
        f"/api/entries/{staff_entry['id']}/sections/staff_note",
        headers=clinician_headers,
        json={"content": "Clinician overwrite attempt", "base_version": 1},
    )
    assert response.status_code == 403

    clinician_entry = client.post(
        "/api/patients/patient-amina/entries",
        headers=clinician_headers,
        json={"title": "Clinical plan", "content": "Review medicines."},
    ).json()
    response = client.patch(
        f"/api/entries/{clinician_entry['id']}/sections/clinician_note",
        headers=staff_headers,
        json={"content": "Staff overwrite attempt", "base_version": 1},
    )
    assert response.status_code == 403


def test_patient_cannot_access_internal_comments_or_raw_ai_notes(client, auth):
    patient_headers = auth("patient")
    assert client.get("/api/patients/patient-amina/timeline", headers=patient_headers).status_code == 403
    assert client.get("/api/patients/patient-amina/glance", headers=patient_headers).status_code == 403

    response = client.get("/api/patient-facing-items", headers=patient_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload and all(item["approved"] for item in payload)
    serialized = str(payload).lower()
    assert "comment" not in serialized
    assert "raw" not in serialized
    assert "ai_" not in serialized


def test_patient_entry_is_intentional_write_only_input(client, auth):
    patient_headers = auth("patient")
    response = client.post(
        "/api/patients/patient-amina/entries",
        headers=patient_headers,
        json={"title": "Question for care team", "content": "Please clarify the follow-up instruction."},
    )
    assert response.status_code == 201
    assert response.json()["sections"][0]["key"] == "patient_input"
    assert client.get("/api/patients/patient-amina/timeline", headers=patient_headers).status_code == 403


def test_clinic_scope_is_enforced_server_side(client, auth, db):
    db.add(Clinic(id="clinic-other", name="Other Clinic"))
    db.add(
        Patient(
            id="patient-other",
            clinic_id="clinic-other",
            display_code="OTHER-1",
            name_encrypted=cipher.encrypt("Other Patient"),
        )
    )
    db.commit()
    response = client.get("/api/patients/patient-other/glance", headers=auth("clinician"))
    assert response.status_code == 404
