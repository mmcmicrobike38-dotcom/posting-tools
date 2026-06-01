from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas as pd

from .parser import (
    NUMERIC_FIELDS,
    actual_collection,
    generate_transaction_key,
    missing_simsoft_columns,
    normalize_text,
    parse_account,
    parse_amount,
    parse_date,
    parse_reference,
)


def parse_and_validate_simsoft(simsoft_df: pd.DataFrame, duplicate_history: set[str]) -> tuple[pd.DataFrame, list[str]]:
    missing_columns = missing_simsoft_columns(simsoft_df)
    if missing_columns:
        return pd.DataFrame(), [f"Missing SIMSOFT columns: {', '.join(missing_columns)}"]

    records: list[dict[str, Any]] = []
    seen_in_batch: set[str] = set()
    for raw_row in simsoft_df.to_dict("records"):
        if (
            not normalize_text(raw_row.get("Account Name"))
            and not normalize_text(raw_row.get("Reference"))
        ):
            continue

        issues: list[str] = []
        parsed: dict[str, Any] = {
            "Account Name": normalize_text(raw_row.get("Account Name")),
            "Reference": normalize_text(raw_row.get("Reference")),
            "Code": normalize_text(raw_row.get("Code")),
        }
        if not parsed["Account Name"]:
            issues.append("Missing Account Name")
        if not parsed["Reference"]:
            issues.append("Missing Reference")

        try:
            parsed["Account Number"], parsed["Account Name Only"] = parse_account(parsed["Account Name"])
        except ValueError as exc:
            issues.append(str(exc))
        try:
            parsed["OR Number"], parsed["Particulars"] = parse_reference(parsed["Reference"])
        except ValueError as exc:
            parsed["OR Number"], parsed["Particulars"] = "", ""
            issues.append(str(exc))
        try:
            parsed["Date"] = parse_date(raw_row.get("Date"))
        except ValueError as exc:
            parsed["Date"] = normalize_text(raw_row.get("Date"))
            issues.append(str(exc))
        for field in NUMERIC_FIELDS:
            try:
                value = raw_row.get(field)
                if field in {"Rebate", "Interest", "Balance"} and not normalize_text(value):
                    parsed[field] = Decimal("0.00")
                else:
                    parsed[field] = parse_amount(value)
            except ValueError as exc:
                parsed[field] = normalize_text(raw_row.get(field))
                issues.append(f"Invalid {field}: {exc}")
        try:
            parsed["Actual Collection"] = actual_collection(parsed.get("Amount"), parsed.get("Interest"))
        except ValueError:
            parsed["Actual Collection"] = Decimal("0.00")

        transaction_key = ""
        if not issues:
            transaction_key = generate_transaction_key(parsed)
        duplicate = transaction_key and (transaction_key in duplicate_history or transaction_key in seen_in_batch)
        if duplicate:
            status, issue = "DUPLICATE", "Duplicate transaction"
        elif issues:
            status, issue = "ERROR", "; ".join(issues)
        else:
            status, issue = "PASSED", ""
            seen_in_batch.add(transaction_key)

        records.append({**parsed, "Status": status, "Issue": issue, "Transaction Key": transaction_key})
    return pd.DataFrame(records), []


def calculate_summary(preview_df: pd.DataFrame) -> dict[str, Any]:
    if preview_df.empty:
        return {
            "Total Rows": 0,
            "Passed Rows": 0,
            "Duplicate Rows": 0,
            "Error Rows": 0,
            "Amount Total": Decimal("0.00"),
            "Interest Total": Decimal("0.00"),
            "Rebate Total": Decimal("0.00"),
            "Actual Collection Total": Decimal("0.00"),
        }
    passed = preview_df[preview_df["Status"] == "PASSED"]
    return {
        "Total Rows": int(len(preview_df)),
        "Passed Rows": int((preview_df["Status"] == "PASSED").sum()),
        "Duplicate Rows": int((preview_df["Status"] == "DUPLICATE").sum()),
        "Error Rows": int((preview_df["Status"] == "ERROR").sum()),
        "Amount Total": sum((parse_amount(v) for v in passed["Amount"]), Decimal("0.00")),
        "Interest Total": sum((parse_amount(v) for v in passed["Interest"]), Decimal("0.00")),
        "Rebate Total": sum((parse_amount(v) for v in passed["Rebate"]), Decimal("0.00")),
        "Actual Collection Total": sum((parse_amount(v) for v in passed["Actual Collection"]), Decimal("0.00")),
    }


def reconciliation_variance(scr_total: Any, manual_total: Any) -> Decimal:
    return (parse_amount(scr_total) - parse_amount(manual_total)).quantize(Decimal("0.01"))


def can_confirm_post(
    connection_ok: bool,
    file_valid: bool,
    has_blocking_errors: bool,
    confirm_text: str,
    live_posting_enabled: bool,
    auth_signed_in: bool = True,
) -> bool:
    return (
        connection_ok
        and file_valid
        and not has_blocking_errors
        and confirm_text == "CONFIRM"
        and live_posting_enabled
        and auth_signed_in
    )


def can_swipe_to_post(
    connection_ok: bool,
    file_valid: bool,
    has_blocking_errors: bool,
    live_posting_enabled: bool,
    auth_signed_in: bool = True,
    preview_fresh: bool = True,
    target_branch_selected: bool = True,
    folder_scan_complete: bool = True,
    branch_unlocked: bool = True,
) -> bool:
    return (
        connection_ok
        and file_valid
        and not has_blocking_errors
        and live_posting_enabled
        and auth_signed_in
        and preview_fresh
        and target_branch_selected
        and folder_scan_complete
        and branch_unlocked
    )
