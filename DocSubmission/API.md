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
| `POST /patients/{id}/entries` | patient, staff, clinician, admin | Create the caller's role-owned manual section. A linked patient may submit `patient_input`, but cannot read the internal timeline afterward. |
| `POST /patients/{id}/interactions` | matched role | Persist encrypted raw text and enqueue processing; returns `202`. |

An interaction request contains `interaction_type`, `content` and optional `synthetic_risk_tag`. Doctor consults require clinician role, nurse consults require staff role, and AI-patient sessions require the linked patient. This intentional patient write path supports patient-contributed insights without exposing internal entries; patient-visible output is only an approved `PatientFacingItem`.

## Processing jobs

| Method and path | Purpose |
|---|---|
| `GET /jobs/{id}` | Read `pending`, `processing`, `complete` or `failed` state plus persisted candidate-level trust outcomes and their counts. |
| `POST /jobs/{id}/retry` | Retry only a pending or failed job. |

Provider failures preserve the encrypted raw interaction and previous Glance snapshot. `error_code` is deliberately short and contains no source content.

Completed jobs expose `trust_summary` counts and an `outcomes` array. Every provider candidate produces a persisted `verified`, `supported` or `review_required` outcome; an empty eligible batch produces one `abstained` outcome. Reason codes such as `unknown_source_ref`, `evidence_not_found`, `provider_output_invalid` and `provider_returned_no_candidates` contain no source text. Only successful matches carry a provenance ID, and patient callers do not receive that internal ID.

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

The trust outcome vocabulary is fixed: `verified` means a backend-validated exact quote match; `supported` means a backend-validated normalized match; `review_required` means the candidate is missing, malformed or points to the wrong source; `abstained` means the provider or policy produced no eligible claim. Multiple matches are preserved as separate immutable source spans and explicitly labelled with `multiple_sources`. Only `verified` and `supported` can enter Glance. `review_required` and `abstained` create no automatic highlight.

### `GET /provenance/{edge_id}`

Returns the primary source fields for compatibility plus `sources`, `source_count` and `multiple_sources`. Every source contains immutable entry/version IDs, backend-derived redacted and original offsets, exact quote, match method, source-support label and a fresh integrity result. It returns `409` if any stored hash no longer agrees with its immutable snapshot.

### `POST /highlights/{id}/feedback`

Action is one of `accept`, `reject`, `pin`, `unpin`, `highlight`, `unhighlight`, `comment`, `edit`, `confirm_warning`. Pin and highlight state are viewer-specific; `unpin` and `unhighlight` remove those display states without creating negative preference feedback. Only a clinician may confirm a warning. A reject affects that care-team member's preference profile and cannot remove a critical-floor item.

Every Glance response exposes `risk_floor` and a score breakdown containing `learned_bonus`; the UI labels these as **Risk floor** and **Learned bonus**.

## Conflicts

- `GET /conflicts?patient_id=...` returns both source-supported facts in every conflict.
- `POST /conflicts/{id}/resolve` is clinician-only and accepts `winning_fact_id` plus a required reason. It marks the other fact superseded without deleting either source.

## PatientFacingItem

- `GET /patient-facing-items`: patient scope is inferred from the token and only approved rows are returned.
- `POST /patient-facing-items`: clinician-only creation/approval of a summary or instruction.

Patients cannot call timeline, Glance, provenance, internal comments, versions or audit endpoints.
