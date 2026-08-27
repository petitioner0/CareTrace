from __future__ import annotations

from app.redaction import assert_no_known_phi, redact


def test_redaction_preserves_a_reversible_boundary_map():
    original = "Amina Rahman called +65 8123 4567 about the lab."
    result = redact(original, ["Amina Rahman"])
    assert "Amina Rahman" not in result.redacted_text
    assert "8123 4567" not in result.redacted_text
    assert len(result.boundary_map) == len(result.redacted_text) + 1
    assert_no_known_phi(result.redacted_text, ["Amina Rahman"])

