"""Forensic accounting analysis for earnings manipulation detection"""

from .metrics import (
    compute_altman_z_score,
    compute_beneish_m_score,
    compute_forensics_score,
    compute_sloan_accruals,
)

__all__ = [
    "compute_beneish_m_score",
    "compute_altman_z_score",
    "compute_sloan_accruals",
    "compute_forensics_score",
]
