"""HRD-404: backend legal content — ToS + privacy policy, localized es/en, versioned + dated.

The in-app legal documents (terms of service + privacy policy) the mobile app links from the
onboarding and settings surfaces must exist in the backend content registry, in both the Spanish
(default) and English catalogs, and be versioned + dated per revision.
"""

from __future__ import annotations

from app.application.legal_content import LEGAL_DOCUMENTS, get_legal_content


def test_the_legal_content_registry_covers_tos_and_privacy_in_both_locales() -> None:
    """HRD-404: ToS + privacy policy ship in the Spanish default and the English catalog."""
    for document_id in ("terms_of_service", "privacy_policy"):
        spanish = get_legal_content(document_id, locale="es")
        english = get_legal_content(document_id, locale="en")
        assert spanish is not None, f"missing Spanish legal content: {document_id}"
        assert english is not None, f"missing English legal content: {document_id}"


def test_the_legal_content_documents_are_versioned_and_dated() -> None:
    """HRD-404: every legal document is versioned and carries an effective date."""
    assert LEGAL_DOCUMENTS, "the legal content registry must not be empty"
    for document in LEGAL_DOCUMENTS:
        assert document.version, f"legal document {document.document_id} needs a version"
        assert document.effective_date is not None, (
            f"legal document {document.document_id} needs an effective date"
        )
