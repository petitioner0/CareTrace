from __future__ import annotations


def test_similar_highlights_gain_priority_and_critical_floor_survives_rejection(client, auth):
    headers = auth("clinician")
    before = client.get("/api/patients/patient-amina/glance", headers=headers).json()["items"]
    dosage_items = [item for item in before if item["entity_type"] == "dosage"]
    assert len(dosage_items) >= 2
    target = dosage_items[0]
    peer = dosage_items[1]
    peer_before = peer["score_breakdown"]["learned_bonus"]

    response = client.post(
        f"/api/highlights/{target['id']}/feedback",
        headers=headers,
        json={"action": "pin"},
    )
    assert response.status_code == 200
    after = client.get("/api/patients/patient-amina/glance", headers=headers).json()["items"]
    peer_after = next(item for item in after if item["id"] == peer["id"])
    assert peer_after["score_breakdown"]["learned_bonus"] > peer_before

    critical = next(item for item in after if item["risk_floor"] >= 90)
    client.post(
        f"/api/highlights/{critical['id']}/feedback",
        headers=headers,
        json={"action": "reject"},
    )
    final_items = client.get("/api/patients/patient-amina/glance", headers=headers).json()["items"]
    critical_after = next(item for item in final_items if item["id"] == critical["id"])
    assert critical_after["score"] >= 90


def test_plain_symptom_text_does_not_create_a_risk_floor(client, auth, db):
    headers = auth("clinician")
    response = client.post(
        "/api/patients/patient-amina/interactions",
        headers=headers,
        json={"interaction_type": "doctor_consult", "content": "Patient reports a symptom of headache."},
    )
    assert response.status_code == 202
    from app.models import Highlight

    symptom = next(item for item in db.query(Highlight).all() if "headache" in item.text.lower())
    assert symptom.risk_floor == 0
    assert symptom.risk_source is None


def test_resolving_conflict_removes_only_the_conflict_floor(client, auth, db):
    from app.models import ClinicalFact, Highlight

    headers = auth("clinician")
    conflict = next(item for item in client.get("/api/conflicts?patient_id=patient-amina", headers=headers).json() if item["status"] == "open")
    response = client.post(
        f"/api/conflicts/{conflict['id']}/resolve",
        headers=headers,
        json={"winning_fact_id": conflict["fact_b"]["id"], "reason": "Verified against the synthetic prescription."},
    )
    assert response.status_code == 200
    for fact_id in (conflict["fact_a"]["id"], conflict["fact_b"]["id"]):
        fact = db.get(ClinicalFact, fact_id)
        highlight = db.query(Highlight).filter_by(provenance_edge_id=fact.provenance_edge_id).one()
        assert highlight.risk_source is None
        assert highlight.risk_floor == 0
