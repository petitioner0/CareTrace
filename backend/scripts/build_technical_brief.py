from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output" / "pdf" / "CareTrace_Technical_Brief.pdf"

INK = colors.HexColor("#18342E")
GREEN = colors.HexColor("#176C57")
PALE = colors.HexColor("#EAF3EE")
LINE = colors.HexColor("#D6E2DC")
MUTED = colors.HexColor("#647770")
AMBER = colors.HexColor("#A76500")
RED = colors.HexColor("#B0342C")


class BriefDoc(BaseDocTemplate):
    def __init__(self, filename: str):
        super().__init__(filename, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=20 * mm, bottomMargin=17 * mm)
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="normal")
        self.addPageTemplates(PageTemplate(id="brief", frames=[frame], onPage=self.draw_page))

    @staticmethod
    def draw_page(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(18 * mm, 14 * mm, 192 * mm, 14 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 9.5 * mm, "CARETRACE  |  SYNTHETIC DATA ONLY  |  NOT CLINICAL DECISION SUPPORT")
        canvas.drawRightString(192 * mm, 9.5 * mm, f"{doc.page} / 3")
        canvas.restoreState()


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="Kicker", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=7.5, leading=9, textColor=GREEN, spaceAfter=5, tracking=1.2))
styles.add(ParagraphStyle(name="Hero", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=28, leading=31, textColor=INK, alignment=TA_LEFT, spaceAfter=8))
styles.add(ParagraphStyle(name="Deck", parent=styles["Normal"], fontName="Helvetica", fontSize=10.3, leading=14.2, textColor=MUTED, spaceAfter=13))
styles.add(ParagraphStyle(name="H1x", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=INK, spaceBefore=8, spaceAfter=7))
styles.add(ParagraphStyle(name="H2x", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=GREEN, spaceBefore=6, spaceAfter=4))
styles.add(ParagraphStyle(name="Bodyx", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.6, leading=11.7, textColor=INK, spaceAfter=6))
styles.add(ParagraphStyle(name="Smallx", parent=styles["BodyText"], fontName="Helvetica", fontSize=7.5, leading=10, textColor=MUTED))
styles.add(ParagraphStyle(name="Boxx", parent=styles["BodyText"], fontName="Helvetica", fontSize=8, leading=10.5, textColor=INK))
styles.add(ParagraphStyle(name="Metric", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=18, leading=20, textColor=GREEN, alignment=1))
styles.add(ParagraphStyle(name="DarkLabel", parent=styles["Kicker"], textColor=colors.HexColor("#9ED2C2"), spaceAfter=0))
styles.add(ParagraphStyle(name="DarkText", parent=styles["Boxx"], textColor=colors.white))


def P(text: str, style: str = "Bodyx") -> Paragraph:
    return Paragraph(text, styles[style])


def section(title: str, body: str):
    return KeepTogether([P(title, "H1x"), P(body)])


def architecture_table():
    rows = [
        [P("React / Vite", "Boxx"), P("REST / JSON + signed token", "Boxx"), P("FastAPI + RBAC", "Boxx")],
        [P("Fast UI", "Smallx"), P("Clinic scope on every call", "Smallx"), P("Service + validation", "Smallx")],
        [P("Precomputed Glance", "Boxx"), P("SQLAlchemy", "Boxx"), P("Encrypted SQLite", "Boxx")],
    ]
    table = Table(rows, colWidths=[53 * mm, 64 * mm, 53 * mm], rowHeights=[12 * mm, 9 * mm, 12 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PALE), ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#F4F7F5")),
        ("BOX", (0, 0), (-1, -1), .6, LINE), ("INNERGRID", (0, 0), (-1, -1), .4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]))
    return table


def flow_table():
    labels = ["RAW", "REDACT", "CANDIDATE", "MATCH", "CITE", "GLANCE"]
    cells = []
    for index, label in enumerate(labels):
        cells.append(P(f"<b>{label}</b>", "Boxx"))
        if index < len(labels) - 1:
            cells.append(P("&#8594;", "Boxx"))
    widths = []
    for index in range(len(cells)):
        widths.append(25 * mm if index % 2 == 0 else 5 * mm)
    table = Table([cells], colWidths=widths, rowHeights=[13 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white), ("BOX", (0, 0), (-1, -1), .6, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TEXTCOLOR", (0, 0), (-1, -1), GREEN),
    ]))
    return table


def build():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = BriefDoc(str(OUTPUT))
    story = [
        P("NIGHTINGALE 72 HOUR BUILD  /  TECHNICAL BRIEF", "Kicker"),
        P("CareTrace", "Hero"),
        P("A provenance-first longitudinal care note that compresses fragmented interactions for action while keeping every AI-supported highlight anchored to immutable evidence.", "Deck"),
        architecture_table(), Spacer(1, 7 * mm), flow_table(), Spacer(1, 5 * mm),
        section("Why this shape", "Healthcare collaboration needs compression, but trust fails when a summary cannot show where it came from. CareTrace therefore treats AI output as a candidate, not a fact. The backend validates evidence, owns offsets, stores provenance, and may abstain. Page loads read a precomputed snapshot and never wait for an LLM."),
        P("Trust boundary", "H2x"),
        P("Raw interactions are committed and encrypted before AI work. Known names, phones and IC/ID patterns are redacted and checked before a provider call. Provider failures preserve the source and previous Glance. Logs and audit events contain metadata only."),
        P("Provider boundary", "H2x"),
        P("Ollama chat and embedding calls sit behind explicit provider interfaces. AI_PROVIDER=ollama|fixture is selected at startup and never changes silently. The fixture provider makes automated tests and offline evaluation reproducible."),
        Spacer(1, 3 * mm), HRFlowable(width="100%", color=LINE, thickness=.7), Spacer(1, 3 * mm),
        P("Synthetic data only. CareTrace is priority support, not diagnosis or clinical decision support.", "Smallx"),
        PageBreak(),
        P("02  /  PROVENANCE, COLLABORATION AND RANKING", "Kicker"),
        P("Evidence before emphasis", "Hero"),
        section("Backend-owned provenance", "The LLM returns source_ref, a verbatim evidence_quote and a normalized candidate - never character offsets. The backend searches only the referenced immutable source version. A unique exact match is verified; a unique Unicode/whitespace-normalized match is supported. Missing or repeated matches are review_required and cannot become automatic highlights."),
        P("Redaction creates a boundary map from redacted positions to the encrypted original. The stored ProvenanceEdge contains source entry/version, section, both coordinate systems, match method and a quote hash. Every read revalidates the hash. Later edits create new versions, so citations do not drift."),
        P("Relational spine", "H1x"),
        Table([
            [P("AUTHORITY", "Kicker"), P("RECORD", "Kicker"), P("TRUST + ACTION", "Kicker")],
            [P("Clinic<br/>User<br/>Patient", "Boxx"), P("Interaction<br/>TimelineEntry<br/>EntrySection<br/>EntryVersion", "Boxx"), P("ClinicalFact<br/>ProvenanceEdge<br/>Highlight<br/>GlanceSnapshot", "Boxx")],
            [P("Signed token<br/>Clinic scope", "Smallx"), P("Role-owned sections<br/>Immutable snapshots", "Smallx"), P("Comment / Conflict<br/>Feedback / Audit", "Smallx")],
        ], colWidths=[49 * mm, 61 * mm, 60 * mm], style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PALE), ("BACKGROUND", (0, 1), (-1, -1), colors.white),
            ("BOX", (0, 0), (-1, -1), .6, LINE), ("INNERGRID", (0, 0), (-1, -1), .4, LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ])),
        P("Deterministic collaboration", "H1x"),
        P("Staff and clinicians own separate sections. Independent section counters allow simultaneous edits without overwriting each other; a stale same-section write returns 409. Revert restores one authorized section into a new version. Conflicting allergy or dosage facts enter a review queue; only a clinician can select the authoritative fact, and both sources remain."),
        P("Bounded adaptive ranking", "H1x"),
        P("<b>final = max(applicable risk floor, clamp(rule score + learned bonus, 0, 100))</b>"),
        P("Risk floors are intentionally narrow: explicit synthetic risk tag, allergy conflict, dosage conflict, critical unresolved action or clinician-confirmed warning. Generic symptoms never create a floor. Clinical entities affect ordering only, not diagnosis."),
        P("Explicit positive and negative feedback updates per-user embedding centroids. The similarity bonus is clamped to +/-8; non-interaction is ignored; critical floors cannot be suppressed."),
        PageBreak(),
        P("03  /  SECURITY, EVALUATION AND SCOPE", "Kicker"),
        P("Know when the system is wrong", "Hero"),
        Table([
            [P("VERIFIED", "Kicker"), P("SUPPORTED", "Kicker"), P("ABSTAIN", "Kicker")],
            [P("Unique exact quote<br/>Schema valid", "Boxx"), P("Unique normalized match<br/>Visible label", "Boxx"), P("Missing / repeated quote<br/>No automatic highlight", "Boxx")],
        ], colWidths=[56.5 * mm] * 3, style=TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), PALE), ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#EEF2F7")),
            ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#FFF1EE")), ("BOX", (0, 0), (-1, -1), .6, LINE),
            ("INNERGRID", (0, 0), (-1, -1), .4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ])), Spacer(1, 5 * mm),
        P("Security and patient boundary", "H1x"),
        P("Passwords use scrypt and tokens use HMAC-SHA256. Every query rechecks subject, role and clinic against SQLite. Patients are linked to one patient ID and can read only clinician-approved summary/instruction rows; timeline, Glance, provenance, versions, comments and audit endpoints reject their token. Local HTTP is for demonstration only; deployment requires TLS termination and managed secrets."),
        P("Automated evaluation", "H1x"),
        P("The required five micro-test modules cover cross-role writes, patient exclusions, clinic isolation, version increments, revert, metadata-only audit, immutable provenance, concurrent sections, deterministic 409 conflicts and adaptive importance. Additional tests verify that LLM offsets are ignored, ambiguous quotes abstain, PHI never reaches a spy provider, ordinary symptom text creates no risk floor and critical items survive rejection."),
        Table([
            [P("1.16 ms", "Metric"), P("1.44 ms", "Metric"), P("< 300 ms", "Metric")],
            [P("median", "Smallx"), P("P95", "Smallx"), P("target", "Smallx")],
        ], colWidths=[56.5 * mm] * 3, rowHeights=[11 * mm, 7 * mm], style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), PALE), ("BOX", (0, 0), (-1, -1), .6, LINE),
            ("INNERGRID", (0, 0), (-1, -1), .4, LINE), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ])), Spacer(1, 3 * mm),
        P("Warm-path approximation: local in-process HTTP client, 500 timeline entries, 20 warm-up requests and 500 measured GET /glance requests. This isolates application/database time and excludes proxy, network and production concurrency effects.", "Smallx"),
        P("Scope and migration", "H1x"),
        P("Configurable prototype defaults are DATA_DECAY_THRESHOLD_DAYS=90, RECENT_CONTEXT_COUNT=3, RAG_TOP_K=5 and GLANCE_MAX_ITEMS=5. Voice, cloud deployment, real EHR integration and formal compliance are out of scope. A production migration would add a durable queue, managed database, key rotation, operational telemetry, extraction datasets and reviewed clinical governance before real patient use."),
        Spacer(1, 3 * mm),
        Table([[P("DESIGN PRINCIPLE", "DarkLabel"), P("Compression may be probabilistic. Provenance, permissions and overrides are deterministic.", "DarkText")]], colWidths=[42 * mm, 128 * mm], style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#143C32")), ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ])),
    ]
    doc.build(story)
    print(OUTPUT)


if __name__ == "__main__":
    build()
