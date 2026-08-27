from __future__ import annotations

import statistics
import time

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal
from app.main import app
from app.models import EntrySection, TimelineEntry


def main() -> None:
    with TestClient(app) as client:
        db = SessionLocal()
        existing = db.scalar(select(func.count()).select_from(TimelineEntry).where(TimelineEntry.patient_id == "patient-amina")) or 0
        for index in range(existing, 500):
            entry = TimelineEntry(
                clinic_id="clinic-demo",
                patient_id="patient-amina",
                author_id="user-staff",
                author_role="staff",
                entry_type="staff_manual_note",
                title=f"Synthetic benchmark note {index + 1}",
            )
            db.add(entry)
            db.flush()
            db.add(EntrySection(entry_id=entry.id, section_key="staff_note", content="Synthetic benchmark context."))
        db.commit()
        total_entries = db.scalar(select(func.count()).select_from(TimelineEntry).where(TimelineEntry.patient_id == "patient-amina"))
        db.close()
        token = client.post(
            "/api/auth/token",
            json={"email": "clinician@caretrace.demo", "password": "demo123"},
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        for _ in range(20):
            client.get("/api/patients/patient-amina/glance", headers=headers)
        timings = []
        for _ in range(500):
            start = time.perf_counter()
            response = client.get("/api/patients/patient-amina/glance", headers=headers)
            response.raise_for_status()
            timings.append((time.perf_counter() - start) * 1000)
        timings.sort()
        p95 = timings[int(len(timings) * 0.95) - 1]
        print(f"timeline_entries={total_entries} requests=500 median_ms={statistics.median(timings):.2f} p95_ms={p95:.2f} target_ms=300")
        raise SystemExit(0 if p95 <= 300 else 1)


if __name__ == "__main__":
    main()
