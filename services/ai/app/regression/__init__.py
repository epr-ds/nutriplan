"""Allergy / exclusion safety regression set: the no-allergen guarantee (AIA-704).

A golden corpus of constraint cases (:data:`~app.regression.corpus.GOLDEN_SAFETY_CASES`) the
production allergen / exclusion filter must satisfy on every run: every unsafe recipe removed,
every safe one kept, and no forbidden ingredient surviving.
:class:`~app.regression.verifier.SafetyRegressionVerifier` grades the corpus into a
:class:`~app.regression.verifier.RegressionReport` whose ``ok`` flag gates release -- a newly
leaking allergen or a lost allergen-family expansion fails the dedicated ``regression`` CI suite.
"""

from app.regression.case import CaseOutcome, SafetyCase
from app.regression.corpus import GOLDEN_SAFETY_CASES
from app.regression.verifier import RegressionReport, SafetyRegressionVerifier

__all__ = [
    "GOLDEN_SAFETY_CASES",
    "CaseOutcome",
    "RegressionReport",
    "SafetyCase",
    "SafetyRegressionVerifier",
]
