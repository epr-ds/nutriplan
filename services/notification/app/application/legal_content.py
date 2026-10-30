"""In-app legal content registry (HRD-404).

The ToS + privacy policy copy the mobile app links from the onboarding and settings surfaces,
localized (Spanish default / English secondary) and versioned + dated per revision.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

LEGAL_DOCUMENT_IDS: tuple[str, ...] = ("terms_of_service", "privacy_policy")


@dataclass(frozen=True)
class LegalDocumentContent:
    """One legal document's copy, in every supported language, with its version + effective date."""

    document_id: str
    version: str
    effective_date: date
    spanish_body: str
    english_body: str

    def body_for(self, *, locale: str) -> str:
        """The document's body for ``locale``; Spanish is the default catalog language."""
        return self.spanish_body if locale == "es" else self.english_body


@dataclass(frozen=True)
class LegalDocumentRevision:
    """The catalog revision a :class:`LegalDocumentContent` was published under."""

    document_id: str
    version: str
    effective_date: date
    spanish_body: str
    english_body: str


LEGAL_DOCUMENTS: tuple[LegalDocumentRevision, ...] = (
    LegalDocumentRevision(
        document_id="terms_of_service",
        version="2026-10-28",
        effective_date=date(2026, 10, 28),
        spanish_body=(
            "Términos del servicio Nutriplan: el uso de la app implica aceptación de estos "
            "términos. Las recetas y planes son orientación nutricional; consulta con un "
            "profesional de la salud antes de cambiar una dieta. Los datos se tratan conforme a la "
            "política de privacidad."
        ),
        english_body=(
            "Nutriplan terms of service: use of the app implies acceptance of these terms. "
            "Recipes and plans are nutritional guidance; consult a healthcare professional before "
            "changing a diet. Data is handled per the privacy policy."
        ),
    ),
    LegalDocumentRevision(
        document_id="privacy_policy",
        version="2026-10-28",
        effective_date=date(2026, 10, 28),
        spanish_body=(
            "Política de privacidad Nutriplan: tratamos los datos que proporcionas (cuenta, "
            "preferencias, actividad de planes) para operar el servicio, enviar recordatorios y "
            "mejorar recomendaciones. No vendemos datos personales."
        ),
        english_body=(
            "Nutriplan privacy policy: we process the data you provide (account, preferences, "
            "plan activity) to operate the service, send reminders and improve recommendations. "
            "We do not sell personal data."
        ),
    ),
)


def get_legal_content(document_id: str, *, locale: str) -> LegalDocumentContent | None:
    """Return the legal content for ``document_id`` in ``locale`` (``es`` default / ``en``).

    An unknown document id resolves to ``None``; the Spanish catalog is the default and English the
    secondary, mirroring the notification locale fallback convention.
    """
    revision = next((d for d in LEGAL_DOCUMENTS if d.document_id == document_id), None)
    if revision is None:
        return None
    return LegalDocumentContent(
        document_id=revision.document_id,
        version=revision.version,
        effective_date=revision.effective_date,
        spanish_body=revision.spanish_body,
        english_body=revision.english_body,
    )
