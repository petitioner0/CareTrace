def test_clinician_comment_appears_on_timeline(client, auth):
    headers = auth("clinician")
    created = client.post(
        "/api/patients/patient-amina/entries",
        headers=headers,
        json={"title": "Comment target", "content": "Clinician-authored source note."},
    )
    assert created.status_code == 201

    entry_id = created.json()["id"]
    comment = client.post(
        f"/api/entries/{entry_id}/comments",
        headers=headers,
        json={"content": "Please confirm the follow-up owner."},
    )
    assert comment.status_code == 201

    timeline = client.get("/api/patients/patient-amina/timeline", headers=headers)
    assert timeline.status_code == 200
    entry = next(item for item in timeline.json() if item["id"] == entry_id)
    assert [item["content"] for item in entry["comments"]] == ["Please confirm the follow-up owner."]
