from __future__ import annotations

import re

from .parser import normalize_text

INSTALLMENT_FRACTION = re.compile(r"\b\d{1,2}(?:-\d{1,2})?/\d{1,2}\b")


def _upper(value: str) -> str:
    return normalize_text(value).upper()


def classify_accounts(reference: str) -> str:
    text = _upper(reference)
    if "NO AMOUNT" in text:
        return "NO AMOUNT"
    if "CASH" in text:
        return "CASH"
    if "DP/MI" in text or "DP / MI" in text:
        return "M"
    if "DP" in text:
        return "DP"
    if "CM TO M" in text:
        return "CM TO M"
    if "CM" in text:
        return "CM"
    if "REPO" in text:
        return "REPO"
    if "MI F" in text or "MI P" in text or "MI" in text or INSTALLMENT_FRACTION.search(text):
        return "M"
    return "UNKNOWN"


def classify_daily(particulars: str) -> str:
    text = _upper(particulars)
    if "CASH" in text:
        return "CASH"
    if "DP/MI" in text or "DP / MI" in text:
        return "MI"
    if "DP" in text:
        return "DP"
    if "CM TO M" in text:
        return "CM"
    if "CM" in text:
        return "CM"
    if "REPO" in text:
        return "UNKNOWN"
    if "MI F" in text or "MI P" in text or "MI" in text or INSTALLMENT_FRACTION.search(text):
        return "MI"
    return "UNKNOWN"
