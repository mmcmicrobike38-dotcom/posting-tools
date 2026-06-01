from __future__ import annotations

import hashlib
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd


EXPECTED_SIMSOFT_COLUMNS = [
    "Account Name",
    "Date",
    "Reference",
    "Interest",
    "Amount",
    "Rebate",
    "Balance",
]

NUMERIC_FIELDS = ["Amount", "Rebate", "Interest", "Balance"]


def normalize_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def parse_amount(value: Any) -> Decimal:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        raise ValueError("Missing numeric value")
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return Decimal(str(value)).quantize(Decimal("0.01"))

    text = str(value).strip()
    if not text:
        raise ValueError("Missing numeric value")
    negative = text.startswith("(") and text.endswith(")")
    text = text.replace(",", "").replace("$", "").replace("R", "").strip("() ")
    try:
        amount = Decimal(text).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid numeric value: {value}") from exc
    return -amount if negative else amount


def parse_date(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        raise ValueError("Missing date")
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=False)
    if pd.isna(parsed):
        parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    if pd.isna(parsed):
        raise ValueError(f"Invalid date: {value}")
    return parsed.strftime("%Y-%m-%d")


def parse_account(account_name: Any) -> tuple[str, str]:
    text = normalize_text(account_name)
    if "/" not in text:
        return text, ""
    account_no, name_only = text.split("/", 1)
    return account_no.strip(), name_only.strip()


def parse_reference(reference: Any) -> tuple[str, str]:
    text = normalize_text(reference)
    match = re.match(r"^\s*(\d+)\s*-\s*(.*)$", text)
    if not match:
        raise ValueError("Invalid OR number")
    return match.group(1), match.group(2).strip()


def actual_collection(amount: Any, interest: Any) -> Decimal:
    return (parse_amount(amount) + parse_amount(interest)).quantize(Decimal("0.01"))


def format_decimal(value: Any) -> str:
    amount = value if isinstance(value, Decimal) else parse_amount(value)
    return f"{amount:.2f}"


def generate_transaction_key(row: dict[str, Any]) -> str:
    parts = [
        normalize_text(row.get("Account Name")).upper(),
        parse_date(row.get("Date")),
        normalize_text(row.get("Reference")).upper(),
        format_decimal(row.get("Amount")),
        format_decimal(row.get("Rebate")),
        format_decimal(row.get("Interest")),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def read_simsoft_excel(uploaded_file: Any) -> pd.DataFrame:
    filename = normalize_text(getattr(uploaded_file, "name", "")).lower()
    if filename.endswith(".xls"):
        raise ValueError(
            "Old .xls files are not supported in this build. Open the file in Excel, "
            "then Save As .xlsx and upload the .xlsx file."
        )
    try:
        return pd.read_excel(uploaded_file, engine="openpyxl")
    except Exception as exc:
        raise ValueError(
            "The uploaded file is not a valid .xlsx workbook. Make sure you upload the "
            "actual SIMSOFT Excel export, not a Google Sheets shortcut, browser page, "
            "PDF, CSV renamed as .xlsx, or incomplete download."
        ) from exc


def missing_simsoft_columns(df: pd.DataFrame) -> list[str]:
    return [column for column in EXPECTED_SIMSOFT_COLUMNS if column not in df.columns]


def days_in_month_name(report_month: date) -> str:
    next_month = report_month.replace(day=28) + pd.Timedelta(days=4)
    last_day = (next_month - pd.Timedelta(days=next_month.day)).day
    return f"1-{last_day}"
