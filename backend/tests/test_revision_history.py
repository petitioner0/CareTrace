from __future__ import annotations


def test_edit_increments_version_revert_restores_and_audit_is_metadata_only(client, auth):
    headers = auth("clinician")
    entry = client.post(
        "/api/patients/patient-amina/entries",
        headers=headers,
        json={"title": "Editable plan", "content": "Original plan"},
    ).json()
    entry_id = entry["id"]

    edited = client.patch(
        f"/api/entries/{entry_id}/sections/clinician_note",
        headers=headers,
        json={"content": "Updated plan", "base_version": 1},
    )
    assert edited.status_code == 200
    assert edited.json()["version"] == 2
    assert edited.json()["entry_version"] == 2

    diff = client.get(f"/api/entries/{entry_id}/diff?from_version=1", headers=headers).json()
    assert "Original plan" in diff["changes"]["clinician_note"]
    assert "Updated plan" in diff["changes"]["clinician_note"]

    reverted = client.post(
        f"/api/entries/{entry_id}/revert",
        headers=headers,
        json={"version": 1, "section_key": "clinician_note"},
    )
    assert reverted.status_code == 200
    assert reverted.json()["entry_version"] == 3

    timeline = client.get("/api/patients/patient-amina/timeline", headers=headers).json()
    restored = next(item for item in timeline if item["id"] == entry_id)
    assert restored["sections"][0]["content"] == "Original plan"

    events = client.get(f"/api/audit?resource_id={entry_id}", headers=headers).json()
    assert {event["action"] for event in events} >= {"entry.created", "section.updated", "section.reverted"}
    assert "Original plan" not in str(events)
    assert "Updated plan" not in str(events)

