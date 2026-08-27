# CareTrace - Provenance-first longitudinal care note

**Nightingale 72 Hour Build | Technical Brief | 27 August 2026**

CareTrace is a clinic-scoped collaboration prototype that compresses fragmented care interactions into a fast Top Card without asking users to trust untraceable AI text. Every automatically surfaced fact begins as a verbatim evidence candidate and becomes usable only after deterministic backend matching to an immutable source version. It uses synthetic data only and is not a clinical decision support or diagnostic system.

## Architecture and core flow

The React/Vite client calls a FastAPI REST API. The service layer applies signed-token RBAC, clinic scope, validation and optimistic locking before SQLAlchemy accesses SQLite. Sensitive raw interactions and redaction maps are encrypted with an environment-derived Fernet key. The Ollama provider is behind `LLMProvider` and `EmbeddingProvider` interfaces; a separately configured fixture provider makes tests and offline demonstrations deterministic.

```text
React / Vite
    | REST JSON + signed token
FastAPI -> RBAC -> Service / validation -> SQLAlchemy -> SQLite
                         |
Raw encrypted interaction
    -> deterministic PHI redaction + leak gate
    -> provider returns source_ref + verbatim evidence_quote
    -> backend unique quote matching + schema validation
    -> immutable ProvenanceEdge
    -> timeline summary / fact / highlight
    -> rule score + bounded preference bonus
    -> precomputed GlanceSnapshot
```

Processing is job-shaped. The raw interaction is committed before AI work starts. A provider or validation failure leaves the raw record intact, marks the job failed without logging source content, and keeps the previous Glance available. Page loads query a precomputed snapshot and never wait for an LLM.

## Provenance and abstention

The LLM never supplies offsets. Each context block receives a stable `source_ref`; the provider may only return a verbatim `evidence_quote` and normalized candidate. The backend searches only the referenced source. A unique exact substring is `verified`; a unique Unicode/whitespace-normalized match is `supported`. Missing or repeated matches are `review_required` and cannot become automatic highlights.

Redaction creates a boundary map from every redacted text position to the encrypted original. Once a candidate quote matches, the backend derives both coordinate systems and stores `source_entry_version_id`, section, offsets, quote hash and match method. Reads recompute the hash. Later edits create new versions, so citations continue to resolve to the original source state.

## Data relationships

- `Clinic -> User / Patient` establishes the authorization boundary.
- `Patient -> Interaction -> raw TimelineEntry -> EntryVersion` preserves source material.
- `TimelineEntry -> EntrySection -> EntryVersion` supports role-owned concurrent editing.
- `ClinicalFact -> ProvenanceEdge -> EntryVersion/span` anchors extraction.
- `Highlight -> ClinicalFact/provenance -> GlanceSnapshot` provides the Top Card.
- `CommentThread`, `AuditEvent` and `Conflict` add collaboration and review state.
- `EmbeddingRecord -> PreferenceProfile -> FeedbackEvent` makes ranking adaptive and auditable.
- `PatientFacingItem` is an intentionally small, clinician-approved patient surface.

Full snapshots were chosen over diffs because the synthetic prototype is small and deterministic revert matters more than storage efficiency. Sections have independent versions: staff and clinician edits can succeed concurrently, while two stale writes to the same section produce `409` rather than last-write-wins.

## Ranking without clinical overclaiming

`final_score = max(applicable_risk_floor, clamp(rule_score + learned_bonus, 0, 100))`

The rule score uses recency, unresolved status, clinical entity presence and clinician confirmation only for information ordering. A deterministic risk floor can originate only from an explicit synthetic risk tag, allergy conflict, dosage conflict, critical unresolved action or clinician-confirmed warning. Generic symptom keywords never generate a floor. The system flags conflicts but does not decide which dose, allergy statement or clinical fact is correct.

Each care-team member has positive and negative embedding centroids. Explicit Accept, Pin, Highlight, Comment and Edit signals update the positive centroid; only explicit Reject updates the negative centroid. Non-interaction is ignored to reduce exposure bias. The similarity bonus is clamped to +/-8, and a critical floor is never suppressible by preference.

Prototype context and decay values are configuration, not medical policy: `DATA_DECAY_THRESHOLD_DAYS=90`, `RECENT_CONTEXT_COUNT=3`, `RAG_TOP_K=5`, `GLANCE_MAX_ITEMS=5`. Old source versions are never deleted; unresolved, explicit-risk and clinician-confirmed information is exempt from decay.

## Security, patient boundary and evaluation

Passwords use scrypt and tokens use HMAC-SHA256. Every protected query rechecks the token subject, role and clinic against the database. Patients are linked to one patient ID and cannot call timeline, Glance, provenance, versions, comments or audit endpoints. They receive only approved summary/instruction rows. Staff and clinician sections are separately owned, preventing either role from overwriting the other's record.

Names known from the patient record, phone patterns and IC/ID patterns are redacted before a provider call. A post-redaction leak check blocks the call if these signals remain. Raw content, mappings and logs have separate handling: raw and mappings are encrypted, while logs and audits contain metadata only. Local development uses HTTP; deployment requires TLS termination and managed secrets.

The required automated tests cover cross-role writes, patient response boundaries, clinic isolation, version increments, diffs, revert, audit metadata, immutable provenance, different-section concurrency, same-section conflicts and preference learning. Additional tests prove LLM offsets are ignored, ambiguous quotes abstain, PHI does not reach a spy provider, generic symptom text creates no floor and critical items survive rejection.

Warm-path measurement used a local in-process HTTP client, SQLite containing 500 timeline entries, 20 warm-up requests and 500 measured `GET /glance` requests. Median latency was **1.16 ms** and P95 was **1.44 ms**, below the 300 ms target. This approximates application/database time on one laptop; it excludes internet, reverse-proxy and multi-user production effects.

## Scope decisions

The build prioritizes Glance, collaboration, provenance, RBAC, concurrency and evaluation. Voice capture, production queues, cloud deployment, real EHR integration and formal healthcare compliance are out of scope. SQLite cosine search is appropriate for the synthetic dataset; a production migration would introduce a durable queue, managed relational storage, key rotation, observability, calibrated extraction evaluation and reviewed clinical governance before any real patient use.

