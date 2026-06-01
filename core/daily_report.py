from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from .classifier import classify_daily
from .accounts import cell_value, decimal_to_display, display_sheet_date
from .parser import days_in_month_name, normalize_text


def daily_tab_name(report_month: date) -> str:
    return days_in_month_name(report_month)


def prepare_daily_preview(parsed_df: pd.DataFrame, report_month: date | str) -> pd.DataFrame:
    tab_name = report_month if isinstance(report_month, str) else daily_tab_name(report_month)
    records = []
    for row in parsed_df.to_dict("records"):
        status = row.get("Status", "PASSED")
        issue = row.get("Issue", "")
        if row.get("is_ibp"):
            records.append(
                {
                    "Target Tab": tab_name,
                    "DATE": row.get("Date"),
                    "OR": row.get("OR Number"),
                    "ACCOUNT #": row.get("Account Number"),
                    "ACCOUNT NAME": row.get("Account Name Only"),
                    "PARTICULARS": row.get("Particulars"),
                    "CASH": "",
                    "DP": "",
                    "MI": "",
                    "CM": "",
                    "IBP": row.get("Actual Collection"),
                    "REBATE": row.get("Rebate"),
                    "PEN": row.get("Interest"),
                    "TOTAL": row.get("Actual Collection"),
                    "Status": status,
                    "Issue": issue,
                    "Transaction Key": row.get("Transaction Key"),
                }
            )
            continue
        if row.get("is_other_payment"):
            records.append(
                {
                    "Target Tab": tab_name,
                    "DATE": row.get("Date"),
                    "OR": row.get("OR Number"),
                    "ACCOUNT #": row.get("Account Number"),
                    "ACCOUNT NAME": row.get("Account Name Only"),
                    "PARTICULARS": row.get("Particulars"),
                    "CASH": "",
                    "DP": "",
                    "MI": "",
                    "CM": "",
                    "IBP": "",
                    "OTHERS": row.get("Actual Collection"),
                    "REBATE": "",
                    "PEN": "",
                    "TOTAL": row.get("Actual Collection"),
                    "Status": status,
                    "Issue": issue,
                    "Transaction Key": row.get("Transaction Key"),
                }
            )
            continue
        tx_type = classify_daily(row.get("Particulars", ""))
        if status == "PASSED" and tx_type == "UNKNOWN":
            status, issue = "ERROR", "Unknown Daily transaction type"
        records.append(
            {
                "Target Tab": tab_name,
                "DATE": row.get("Date"),
                "OR": row.get("OR Number"),
                "ACCOUNT #": row.get("Account Number"),
                "ACCOUNT NAME": row.get("Account Name Only"),
                "PARTICULARS": row.get("Particulars"),
                "CASH": row.get("Amount") if tx_type == "CASH" else "",
                "DP": row.get("Amount") if tx_type == "DP" else "",
                "MI": row.get("Amount") if tx_type == "MI" else "",
                "CM": row.get("Amount") if tx_type == "CM" else "",
                "IBP": "",
                "OTHERS": "",
                "REBATE": row.get("Rebate"),
                "PEN": row.get("Interest"),
                "TOTAL": row.get("Actual Collection"),
                "Status": status,
                "Issue": issue,
                "Transaction Key": row.get("Transaction Key"),
            }
        )
    return pd.DataFrame(records)


DAILY_COLUMNS = {
    "DATE": 2,
    "OR": 3,
    "ACCOUNT #": 4,
    "ACCOUNT NAME": 5,
    "PARTICULARS": 6,
    "CASH": 8,
    "DP": 9,
    "MI": 11,
    "REBATE": 12,
    "PEN": 13,
    "CM": 14,
    "IBP": 16,
    "OTHERS": 18,
    "TOTAL": 20,
}


def normalize_daily_header(value: Any) -> str:
    text = normalize_text(value).upper().replace(" ", "")
    aliases = {
        "ACCOUNT#": "ACCOUNT #",
        "ACCOUNTNO": "ACCOUNT #",
        "ACCOUNTNUMBER": "ACCOUNT #",
        "ACCOUNTNAME": "ACCOUNT NAME",
        "PARTICULAR": "PARTICULARS",
        "PENALTY": "PEN",
        "REB": "REBATE",
        "OTHER": "OTHERS",
        "OTHERPAYMENT": "OTHERS",
        "OTHERPAYMENTS": "OTHERS",
    }
    return aliases.get(text, normalize_text(value).upper())


def daily_column_map(sheet_rows: list[list[Any]]) -> dict[str, int]:
    for row in sheet_rows[:10]:
        mapped: dict[str, int] = {}
        for index, value in enumerate(row, start=1):
            header = normalize_daily_header(value)
            if header in DAILY_COLUMNS and header not in mapped:
                mapped[header] = index
        if {"DATE", "OR", "ACCOUNT #", "ACCOUNT NAME", "PARTICULARS"}.issubset(mapped):
            return {**DAILY_COLUMNS, **mapped}
    return DAILY_COLUMNS


def find_blank_daily_rows(sheet_rows: list[list[Any]]) -> list[int]:
    blank_rows: list[int] = []
    columns = daily_column_map(sheet_rows)
    for row_number, row in enumerate(sheet_rows, start=1):
        first_col = normalize_text(cell_value(row, 0))
        if first_col.upper() == "REMARKS":
            break
        if not first_col.isdigit():
            continue
        key_values = [normalize_text(cell_value(row, columns[col] - 1)) for col in ["DATE", "OR", "ACCOUNT #", "ACCOUNT NAME", "PARTICULARS"]]
        if not any(key_values):
            blank_rows.append(row_number)
    return blank_rows


def prepare_daily_sheet_updates(daily_preview: pd.DataFrame, sheet_rows: list[list[Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    updates: list[dict[str, Any]] = []
    errors: list[str] = []
    passed = daily_preview[daily_preview["Status"] == "PASSED"] if "Status" in daily_preview else pd.DataFrame()
    if passed.empty:
        return updates, errors

    blank_rows = find_blank_daily_rows(sheet_rows)
    if len(blank_rows) < len(passed):
        errors.append(f"Not enough blank rows in 1-31 tab. Need {len(passed)}, found {len(blank_rows)}.")
        return updates, errors

    columns = daily_column_map(sheet_rows)
    for target_row, row in zip(blank_rows, passed.to_dict("records")):
        updates.extend(
            [
                {"row": target_row, "col": columns["DATE"], "value": display_sheet_date(row["DATE"])},
                {"row": target_row, "col": columns["OR"], "value": row["OR"]},
                {"row": target_row, "col": columns["ACCOUNT #"], "value": row["ACCOUNT #"]},
                {"row": target_row, "col": columns["ACCOUNT NAME"], "value": row["ACCOUNT NAME"]},
                {"row": target_row, "col": columns["PARTICULARS"], "value": row["PARTICULARS"]},
                {"row": target_row, "col": columns["CASH"], "value": decimal_to_display(row["CASH"]) if row["CASH"] != "" else ""},
                {"row": target_row, "col": columns["DP"], "value": decimal_to_display(row["DP"]) if row["DP"] != "" else ""},
                {"row": target_row, "col": columns["MI"], "value": decimal_to_display(row["MI"]) if row["MI"] != "" else ""},
                {"row": target_row, "col": columns["REBATE"], "value": decimal_to_display(row["REBATE"]) if row["REBATE"] != "" else ""},
                {"row": target_row, "col": columns["PEN"], "value": decimal_to_display(row["PEN"]) if row["PEN"] != "" else ""},
                {"row": target_row, "col": columns["CM"], "value": decimal_to_display(row["CM"]) if row["CM"] != "" else ""},
                {"row": target_row, "col": columns["IBP"], "value": decimal_to_display(row["IBP"]) if row["IBP"] != "" else ""},
                {"row": target_row, "col": columns["OTHERS"], "value": decimal_to_display(row["OTHERS"]) if row.get("OTHERS", "") != "" else ""},
                {"row": target_row, "col": columns["TOTAL"], "value": decimal_to_display(row["TOTAL"]) if row["TOTAL"] != "" else ""},
            ]
        )
    return updates, errors
