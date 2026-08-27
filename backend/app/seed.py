from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .ai import FixtureProvider
from .database import SessionLocal
from .models import Clinic, CommentThread, Patient, PatientFacingItem, TimelineEntry, User
from .security import Principal, cipher, hash_password
from .services import create_interaction, create_manual_entry, process_job


DEMO_PASSWORD = "demo123"


def seed_database(db: Session) -> None:
    if db.scalar(select(Clinic.id)):
        return
    clinic = Clinic(id="clinic-demo", name="Nightingale Community Clinic")
    db.add(clinic)
    users = {
        "clinician": User(
            id="user-clinician",
            clinic_id=clinic.id,
            email="clinician@caretrace.demo",
            display_name="Dr. Maya Chen",
            role="clinician",
            password_hash=hash_password(DEMO_PASSWORD),
        ),
        "staff": User(
            id="user-staff",
            clinic_id=clinic.id,
            email="staff@caretrace.demo",
            display_name="Jordan Lee",
            role="staff",
            password_hash=hash_password(DEMO_PASSWORD),
        ),
        "admin": User(
            id="user-admin",
            clinic_id=clinic.id,
            email="admin@caretrace.demo",
            display_name="Clinic Admin",
            role="admin",
            password_hash=hash_password(DEMO_PASSWORD),
        ),
    }
    patient = Patient(
        id="patient-amina",
        clinic_id=clinic.id,
        display_code="CT-1042",
        name_encrypted=cipher.encrypt("Amina Rahman"),
    )
    second_patient = Patient(
        id="patient-daniel",
        clinic_id=clinic.id,
        display_code="CT-1088",
        name_encrypted=cipher.encrypt("Daniel Tan"),
    )
    patient_user = User(
        id="user-patient",
        clinic_id=clinic.id,
        email="patient@caretrace.demo",
        display_name="Amina Rahman",
        role="patient",
        password_hash=hash_password(DEMO_PASSWORD),
        patient_id=patient.id,
    )
    db.add_all([*users.values(), patient_user, patient, second_patient])
    db.commit()

    staff_principal = Principal(users["staff"].id, clinic.id, "staff", None, users["staff"].display_name)
    clinician_principal = Principal(users["clinician"].id, clinic.id, "clinician", None, users["clinician"].display_name)
    old_note = create_manual_entry(
        db,
        patient,
        staff_principal,
        "Initial medication reconciliation",
        "Patient-reported medication list received; clinician verification requested.",
    )
    old_note.created_at = datetime(2025, 4, 15, 9, 30, tzinfo=timezone.utc)
    db.add(
        CommentThread(
            clinic_id=clinic.id,
            entry_id=old_note.id,
            author_id=users["staff"].id,
            content="@Dr. Chen please confirm the medication dose.",
            mention_user_id=users["clinician"].id,
            assigned_to_id=users["clinician"].id,
        )
    )
    db.commit()

    first_text = (
        "Amina Rahman reports an allergy to penicillin. "
        "Medication reconciliation lists Metformin 500 mg twice daily. "
        "The follow-up lab order remains unresolved. Contact +65 8123 4567, ID S1234567D."
    )
    _, first_job = create_interaction(db, patient, clinician_principal, "doctor_consult", first_text, None)
    process_job(first_job.id, SessionLocal, FixtureProvider())

    second_text = (
        "Medication reconciliation now lists Metformin 1000 mg twice daily. "
        "Critical action: clinician must resolve the dosage conflict before the next refill."
    )
    _, second_job = create_interaction(db, patient, staff_principal, "nurse_consult", second_text, None)
    process_job(second_job.id, SessionLocal, FixtureProvider())

    plan_entry = create_manual_entry(
        db,
        patient,
        clinician_principal,
        "Clinician plan",
        "Review the conflicting metformin dose and confirm the active prescription before refill.",
    )
    db.add(
        PatientFacingItem(
            clinic_id=clinic.id,
            patient_id=patient.id,
            item_type="instruction",
            content="Please bring your current medication packaging to your next appointment.",
            approved=True,
            approved_by=users["clinician"].id,
            approved_at=datetime.now(timezone.utc),
            source_entry_id=plan_entry.id,
        )
    )
    db.commit()


def seed_from_factory() -> None:
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()

