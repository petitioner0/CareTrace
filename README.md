# CareTrace

CareTrace is a provenance-first longitudinal care note prototype built for the Nightingale 72 Hour Build. It helps a care team understand the most actionable patient context quickly while keeping every AI-supported highlight traceable to an immutable source version and backend-validated text span.

> Synthetic data only. CareTrace is a collaboration and priority-support prototype, not a clinical decision support system and not a diagnostic tool.

## What is implemented

- Precomputed Glance view with up to five ranked, source-supported highlights and open actions.
- Continuous timeline containing manual, raw-interaction, AI-scribed and system entries.
- Backend-owned provenance: the LLM proposes a verbatim quote; the backend finds the unique span, maps redacted offsets to the encrypted original and stores a hash-bound edge to an immutable entry version.
- Server-side clinic scope and role permissions for patient, staff, clinician and admin users.
- Role-owned note sections, optimistic locking, immutable snapshots, diffs, revert and metadata-only audit events.
- Comments, mentions/assignments in the API, resolve state and an explicit conflict review queue.
- PHI redaction before any provider call and field encryption for raw interactions and redaction maps.
- Pluggable Ollama chat/embedding adapter plus an explicitly selected deterministic fixture provider.
- Preference embeddings with bounded similarity bonuses; critical floors cannot be suppressed.
- A minimal patient view exposing only clinician-approved summaries/instructions.

Trust outcomes use one vocabulary everywhere: `verified` is a backend-validated exact quote match, `supported` is a backend-validated normalized match, `review_required` is a candidate that cannot be resolved safely, and `abstained` means no eligible claim was produced. When evidence matches more than once, every immutable source span is returned and the item is labelled as having multiple sources. Only `verified` and `supported` items can enter Glance; `review_required` and `abstained` never become automatic highlights.

## Quick start

Prerequisites: Python 3.11+, Node.js 20+ and pnpm. Ollama is optional because the default local demo provider is deterministic.

After completing the one-time backend and frontend setup below, start the whole application from the repository root with one command:

```bash
./dev.sh
```

Open `http://127.0.0.1:5173`. The command runs both development servers in one terminal; press `Ctrl+C` once to stop both. It also loads the root `.env` file when present. Optional `CARETRACE_BACKEND_PORT` and `CARETRACE_FRONTEND_PORT` environment variables override the default ports.

### One-time setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
cp ../.env.example ../.env
cd ../frontend
pnpm install
cd ..
```

Then use `./dev.sh` whenever you want to run CareTrace. The API runs at `http://localhost:8000`; interactive OpenAPI is at `http://localhost:8000/docs`.

To run either service separately for debugging, use the original commands:

```bash
cd backend && .venv/bin/python -m uvicorn app.main:app --reload --port 8000
cd frontend && pnpm dev
```

Choose any demo role at `http://localhost:5173`. All accounts use password `demo123`; the UI exchanges it for a signed, short-lived token.

| Role | Email |
|---|---|
| Clinician | `clinician@caretrace.demo` |
| Staff | `staff@caretrace.demo` |
| Patient | `patient@caretrace.demo` |
| Admin | `admin@caretrace.demo` |

## Ollama mode

The application never silently switches providers. Set these values before starting the backend:

```bash
export AI_PROVIDER=ollama
export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_CHAT_MODEL=qwen3:4b
export OLLAMA_EMBED_MODEL=embeddinggemma
```

Ollama must have both configured models available. Use `AI_PROVIDER=fixture` for deterministic offline demonstrations and tests.

## Security and trust boundaries

- `clinic_id` and role are read from a signed token and rechecked against the database. Client-supplied scope is never trusted.
- Patients receive only approved patient-facing rows; their token is rejected by timeline, raw source, comment, audit and Glance endpoints.
- `POST /patients/{id}/entries` intentionally accepts a linked patient's `patient_input` contribution, but it is a write-only internal intake path for that patient: the same patient token still cannot read timeline entries. Patient-visible output is exclusively an approved `PatientFacingItem`.
- Staff and clinicians own separate sections. A clinician cannot overwrite a staff section, and vice versa.
- SQLite + field-level encryption: raw content, redaction maps and patient names are encrypted with Fernet. Set `ENCRYPTION_KEY` to a stable Fernet key outside local demo use; changing it makes prior encrypted data unreadable. The SQLite database file itself is not claimed to be encrypted.
- Known patient names, phone patterns and IC/ID patterns are redacted before the provider call. A post-redaction leak check blocks processing when these signals remain.
- Logs and audit events contain metadata only, never source text, prompts or decrypted fields.
- Local development uses HTTP. A deployed environment must terminate TLS at a trusted reverse proxy and provide secrets through its secret manager.

## Risk policy

CareTrace does not infer clinical danger from generic symptom keywords. A deterministic risk floor can only come from an explicit synthetic risk tag, allergy conflict, dosage conflict, critical unresolved action or clinician-confirmed warning. LLM risk suggestions do not set a floor.

Prototype policy values are configurable:

```text
DATA_DECAY_THRESHOLD_DAYS=90
RECENT_CONTEXT_COUNT=3
RAG_TOP_K=5
GLANCE_MAX_ITEMS=5
```

## Tests and performance

```bash
cd backend
pytest
python scripts/benchmark_glance.py
```

The four required micro-test modules are included, plus the learned bonus `test_self_learning_importance.py`. Additional coverage checks PHI handling, `review_required`/`abstained` outcomes, span integrity and the risk floor boundary. The benchmark warms the API, inserts at least 500 patient timeline entries, performs 500 loopback requests and calculates P95 without invoking an LLM.

## Repository guide

- `backend/app/`: data models, API, security, redaction, provider adapters and business rules.
- `backend/tests/`: required micro-tests plus trust-boundary tests.
- `frontend/src/`: English clinician/staff/admin and patient demo UI.
- `DocSubmission/`: API contract, Markdown technical brief, demo script and submission-ready PDF.

See [API.md](DocSubmission/API.md) for endpoint contracts and [DEMO_SCRIPT.md](DocSubmission/DEMO_SCRIPT.md) for a short recording sequence.
