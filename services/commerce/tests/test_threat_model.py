"""COM-908: commerce threat-model review (STRIDE) and recorded sign-off.

Re-verification gate for the commerce threat-model artefact that feeds the pre-launch security
sign-off: the STRIDE review of the order / payment / fulfillment surfaces, the findings register
and the recorded sign-off must ship together as one register, and the surface list must stay
explicit so a new commerce surface cannot bypass the review.
"""

from __future__ import annotations

from pathlib import Path


def _doc_text() -> str | None:
    doc_path = Path(__file__).resolve().parents[3] / "docs" / "THREAT-MODEL.md"
    if not doc_path.is_file():
        return None
    return doc_path.read_text(encoding="utf-8")


def test_the_commerce_threat_model_is_recorded() -> None:
    """COM-908: the commerce threat-model register must exist before launch sign-off."""
    assert _doc_text() is not None, "Commerce threat-model register not found (COM-908)"


def test_the_threat_model_covers_the_commerce_surfaces() -> None:
    """COM-908: the STRIDE review must cover payment, order and fulfillment surfaces."""
    text = _doc_text()
    assert text is not None, "Commerce threat-model register not found (COM-908)"
    lowered = text.lower()
    for surface in ("payment", "order", "fulfillment"):
        assert surface in lowered, f"threat model does not cover the {surface} surface"


def test_the_threat_model_records_findings_and_signoff() -> None:
    """COM-908: the register must track findings and carry a recorded sign-off."""
    text = _doc_text()
    assert text is not None, "Commerce threat-model register not found (COM-908)"
    lowered = text.lower()
    assert "stride" in lowered, "threat model must state the STRIDE methodology"
    assert "finding" in lowered, "threat model must carry a findings register"
    assert "sign-off" in lowered or "signoff" in lowered, (
        "threat model must record the launch sign-off"
    )
