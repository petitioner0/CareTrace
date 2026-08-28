# CareTrace demo script

Target length: 4-5 minutes. Use the seeded synthetic patient Amina Rahman. Keep the vocabulary visible and consistent: Glance, `verified`, `supported`, `review_required`, `abstained`, Risk floor, Learned bonus and `PatientFacingItem`.

## 1. Glance and source trust (75 seconds)

1. Sign in as **Care staff**.
2. Open Amina Rahman. The first screen shows no more than five ranked items and a separate Open Actions list.
3. Point out the **Critical floor**, **Source support** and score. Expand “Why this?” to show rule score, bounded learned bonus and risk floor.
4. State clearly: CareTrace does not infer clinical danger from symptom text. This critical floor exists because the source contains an explicit critical unresolved action.
5. Open “View exact source.” Show the immutable entry version, backend match method, exact original quote and integrity status.
6. Jump to the source timeline entry.

## 2. Manual highlight, collaboration, concurrency and audit (100 seconds)

1. Open an AI-scribed-note item, use “View exact source” to show the note evidence, then click **Highlight** on that item. Explain that this is an explicit manual signal from an AI note, not passive behavior, and that it contributes only a bounded Learned bonus.
2. In Timeline, add a staff note and an internal comment.
3. Sign in as **Clinician** and show that the staff section is visible but not editable.
4. Edit a clinician-owned section. Open revision history and explain that every edit creates a full immutable snapshot.
5. Explain optimistic locking: separate staff and clinician sections can change concurrently; stale writes to the same section return `409` instead of overwriting work.
6. Open Review Queue. Compare the two source-backed metformin dosage statements. Explain that CareTrace flags the conflict but never chooses the clinically correct value.

## 3. Longitudinal insight (20 seconds)

1. In Timeline, open the **longitudinal insight** entry generated from at least two dated AI-scribed summaries.
2. Point out that it is a source-supported cross-visit view, not a free-floating synthesis: each contributing statement retains provenance to its immutable source version.
3. State the decay rule briefly: recent context is retrieved first; older unresolved, explicit-risk or clinician-confirmed items remain protected.

## 4. Adaptive importance and patient boundary (75 seconds)

1. Return to Glance and Pin a dosage item.
2. Expand a related item's score to show the bounded similarity bonus. Emphasize that explicit Reject is the only negative signal; non-interaction is ignored.
3. Reject the critical action and show that it remains visible at its floor.
4. Sign in as **Patient**. Show only the clinician-approved instruction.
5. Point out that raw AI notes, internal comments, provenance source text and audits are unavailable to the patient token.

## Closing (20 seconds)

Summarize the trust chain: raw encrypted interaction, pre-LLM redaction, structured candidate evidence, backend quote matching, immutable provenance, bounded ranking and explicit human decisions.
