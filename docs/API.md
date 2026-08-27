# CareTrace API contract

Base URL: `http://localhost:8000/api`. JSON is used for requests and responses. Protected endpoints require `Authorization: Bearer <token>`.

## Authentication

### `POST /auth/token`

Request: `{"email":"clinician@caretrace.demo","password":"demo123"}`. Returns a signed token and the user's stable ID, role, clinic scope and optional linked patient ID. Invalid credentials return `401`.

## Patient record

| Method and path | Roles | Purpose |
|---|---|---|
| `GET /patients` | all | Clinic-scoped list; patient receives only their own record. |
| `GET /patients/{id}/glance` | staff, clinician, admin | Read the precomputed viewer-specific Top Card. Never invokes an LLM. |
| `GET /patients/{id}/timeline` | staff, clinician, admin | Read ordered entries, sections and internal comments. |
| `POST /patients/{id}/entries` | all | Create a role-owned manual section. |
| `POST /patients/{id}/interactions` | matched role | Persist encrypted raw text and enqueue processing; returns `202`. |

An interaction request contains `interaction_type`, `content` and optional `synthetic_risk_tag`. Doctor consults require clinician role, nurse consults require staff role, and AI-patient sessions require the linked patient.

## Processing jobs

| Method and path | Purpose |
|---|---|
| `GET /jobs/{id}` | Read `pending`, `processing`, `complete` or `failed` state. |
| `POST /jobs/{id}/retry` | Retry only a pending or failed job. |

Provider failures preserve the encrypted raw interaction and previous Glance snapshot. `error_code` is deliberately short and contains no source content.

## Collaboration and versions

### `PATCH /entries/{entry_id}/sections/{section_key}`

Request: `{"content":"...","base_version":2}`. The server verifies section ownership. A stale base version returns:

```json
{
  "detail": {
    "code": "section_version_conflict",
    "current_version": 3,
    "current_content": "..."
  }
}
```

Different sections have independent counters and may be updated concurrently.

| Method and path | Purpose |
|---|---|
| `GET /entries/{id}/versions` | List immutable snapshots and change metadata. |
| `GET /entries/{id}/diff?from_version=1` | Unified section diff against current version. |
| `POST /entries/{id}/revert` | Restore one role-owned section from an old snapshot while creating a new version. |
| `POST /entries/{id}/comments` | Add internal comment, mention and/or assignment. |
| `PATCH /comments/{id}` | Resolve or reopen a comment. |
| `GET /audit?resource_id=...` | Clinician/admin metadata-only audit events. |

## Provenance and feedback

### `GET /provenance/{edge_id}`

Returns immutable source entry/version IDs, backend-derived redacted and original offsets, exact quote, match method, source-support label and a fresh integrity result. It returns `409` if the stored hash no longer agrees with the immutable snapshot.

### `POST /highlights/{id}/feedback`

Action is one of `accept`, `reject`, `pin`, `highlight`, `comment`, `edit`, `confirm_warning`. Only a clinician may confirm a warning. A reject affects that care-team member's preference profile and cannot remove a critical-floor item.

## Conflicts

- `GET /conflicts?patient_id=...` returns both source-supported facts in every conflict.
- `POST /conflicts/{id}/resolve` is clinician-only and accepts `winning_fact_id` plus a required reason. It marks the other fact superseded without deleting either source.

## Patient-facing items

- `GET /patient-facing-items`: patient scope is inferred from the token and only approved rows are returned.
- `POST /patient-facing-items`: clinician-only creation/approval of a summary or instruction.

Patients cannot call timeline, Glance, provenance, internal comments, versions or audit endpoints.

