from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

import pandas as pd

from .classifier import classify_accounts
from .ibp_resolver import IBP_SECTION_LABEL
from .other_payment import OTHER_PAYMENT_SECTION_LABEL
from .parser import normalize_text, parse_amount, parse_date


ACCOUNTS_HEADERS = [
    "ACCOUNT",
    "DATE",
    "REF",
    "REB",
    "CASH",
    "DP",
    "CM",
    "CM TO M",
    "M",
    "PENALTY",
    "OTHERS",
    "REPO",
    "OUTSTANDING BALANCE",
    "SIMSOFT LEDGER BALANCE",
]
OTHER_PAYMENT_SECTION_LABELS = [OTHER_PAYMENT_SECTION_LABEL, "OTHER PAYMENT", "OTHER PAYMENTS"]
IBP_FROM_SECTION_LABEL = "IBP FROM OTHER BRANCH"
NO_AMOUNT_COLUMN = "NO AMOUNT"


def canonical_header_key(header: Any) -> str:
    key = " ".join(normalize_text(header).upper().split())
    aliases = {
        "CM TO MI": "CM TO M",
        "MI": "M",
        "FULLY PAID DATE": "DATE FULLY PAID",
        "DATE FULLYPAID": "DATE FULLY PAID",
        "SIMSOFT LEDGER BALANCE": "SIMSOFT LEDGER BALANCE",
    }
    return aliases.get(key, key)


def build_header_map(headers: list[str], required: list[str] | None = None) -> dict[str, int]:
    normalized = {canonical_header_key(header): idx for idx, header in enumerate(headers)}
    required_headers = required or ACCOUNTS_HEADERS
    required_keys = [canonical_header_key(header) for header in required_headers]
    missing = [header for header, key in zip(required_headers, required_keys) if key not in normalized]
    if missing:
        raise ValueError(f"Missing target Google Sheet headers: {', '.join(missing)}")
    return {header: normalized[header] for header in normalized}


def cell_value(row: list[Any], index: int) -> Any:
    return row[index] if index < len(row) else ""


def append_line_break(existing: Any, new_value: Any) -> str:
    existing_text = normalize_text(existing)
    new_text = normalize_text(new_value)
    if not existing_text:
        return new_text
    if not new_text:
        return existing_text
    return f"{existing_text}\n{new_text}"


def append_unique_line_break(existing: Any, new_value: Any) -> str:
    existing_text = normalize_text(existing)
    new_text = normalize_text(new_value)
    if not existing_text:
        return new_text
    if not new_text:
        return existing_text
    existing_lines = [normalize_text(line) for line in existing_text.replace("\r", "\n").split("\n")]
    if new_text in existing_lines:
        return existing_text
    return f"{existing_text}\n{new_text}"


def display_sheet_date(value: Any) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return normalize_text(value)
    return f"{parsed.day}-{parsed.strftime('%b-%y')}"


def sum_numeric(existing: Any, addition: Any) -> Decimal:
    existing_text = normalize_text(existing)
    zero_placeholders = {"", "-", "–", "—"}
    base = Decimal("0.00") if existing_text in zero_placeholders else parse_amount(existing)
    return (base + parse_amount(addition)).quantize(Decimal("0.01"))


def subtract_numeric(existing: Any, deduction: Any) -> Decimal:
    existing_text = normalize_text(existing)
    zero_placeholders = {"", "-", "–", "—"}
    base = Decimal("0.00") if existing_text in zero_placeholders else parse_amount(existing)
    return (base - parse_amount(deduction)).quantize(Decimal("0.01"))


def sum_numeric_or_blank(existing: Any, addition: Any) -> str:
    existing_text = normalize_text(existing)
    zero_placeholders = {"", "-", "â€“", "â€”"}
    addition_amount = parse_amount(addition)
    if existing_text in zero_placeholders and addition_amount == Decimal("0.00"):
        return ""
    return decimal_to_display(sum_numeric(existing, addition_amount))


def accounts_ledger_deduction(row: Any) -> Decimal:
    amount_col = normalize_text(row.get("Amount Column", ""))
    principal_payment = parse_amount(row["Amount"]) if amount_col in {"CASH", "DP", "M"} else Decimal("0.00")
    return (
        principal_payment
        + parse_amount(row["Rebate"])
    ).quantize(Decimal("0.01"))


def is_no_amount_column(value: Any) -> bool:
    return normalize_text(value).upper() == NO_AMOUNT_COLUMN or normalize_text(value) == ""


def should_mark_fully_paid(row: Any, projected_balance: Decimal, existing_status: Any) -> bool:
    amount_col = normalize_text(row.get("Amount Column", "")).upper()
    status = normalize_text(existing_status).upper()
    return amount_col != "CASH" and projected_balance == Decimal("0.00") and status == "INSTALLMENT"


def build_fully_paid_cash_export(preview_df: pd.DataFrame, sheet_rows: list[list[Any]], headers: list[str]) -> pd.DataFrame:
    if preview_df.empty or "Status" not in preview_df:
        return pd.DataFrame(columns=["Account", "Code"])
    header_map = build_header_map(headers, ACCOUNTS_HEADERS)
    records: list[dict[str, Any]] = []
    eligible = preview_df[preview_df["Status"].isin(["PASSED", "DUPLICATE"])]
    for row in eligible.to_dict("records"):
        if row.get("is_ibp") or row.get("is_other_payment") or not normalize_text(row.get("Target Row", "")):
            continue
        amount_col = normalize_text(row.get("Amount Column", "")).upper()
        export_type = ""
        target_row = int(row["Target Row"])
        existing = sheet_rows[target_row - 1] if target_row - 1 < len(sheet_rows) else []
        if amount_col == "CASH":
            export_type = "CASH"
        elif "STATUS" in header_map:
            current_status = cell_value(existing, header_map["STATUS"])
            projected_balance = subtract_numeric(
                cell_value(existing, header_map["OUTSTANDING BALANCE"]),
                accounts_ledger_deduction(row),
            )
            if should_mark_fully_paid(row, projected_balance, current_status) or normalize_text(current_status).upper() == "FULLY PAID":
                export_type = "FULLY PAID"
        if export_type:
            records.append(
                {
                    "Account": row.get("Account Name", ""),
                    "Code": cell_value(existing, header_map["CODE"]) if "CODE" in header_map else "",
                    "Type": export_type,
                }
            )
    return pd.DataFrame(records, columns=["Account", "Code", "Type"])


def build_account_index(sheet_rows: list[list[Any]], headers: list[str], header_row: int) -> dict[str, dict[str, Any]]:
    header_map = build_header_map(headers, ["ACCOUNT"])
    account_col = header_map["ACCOUNT"]
    index: dict[str, dict[str, Any]] = {}
    for zero_based_idx, row in enumerate(sheet_rows[header_row:], start=header_row + 1):
        account = normalize_text(cell_value(row, account_col))
        if account:
            index[account.upper()] = {"row_number": zero_based_idx, "values": row}
    return index


def find_section_row(sheet_rows: list[list[Any]], section_label: str, header_row: int) -> dict[str, Any] | None:
    target_label = normalize_text(section_label).upper()
    for row_number, row in enumerate(sheet_rows[header_row:], start=header_row + 1):
        for col_index, value in enumerate(row, start=1):
            if normalize_text(value).upper() == target_label:
                return {"row_number": row_number, "values": row, "label_col": col_index}
    return None


def _section_amount_col(section_row: list[Any], label_col: int) -> int:
    for col in range(label_col + 1, min(label_col + 9, len(section_row) + 1)):
        text = normalize_text(cell_value(section_row, col - 1))
        if text in {"-", " - ", "–", "—"}:
            return col
        if text.startswith("(") and text.endswith(")"):
            return col
    return label_col + 5


def _section_cell_is_empty(value: Any) -> bool:
    text = normalize_text(value)
    return text in {"", "-", " - ", "–", "—"}


def find_section_posting_target(sheet_rows: list[list[Any]], section_label: str, header_row: int) -> dict[str, Any] | None:
    section = find_section_row(sheet_rows, section_label, header_row)
    if not section:
        return None

    text_col = int(section["label_col"])
    amount_col = _section_amount_col(section["values"], text_col)
    row_number = int(section["row_number"]) + 1
    while row_number <= len(sheet_rows):
        row = sheet_rows[row_number - 1]
        text_value = normalize_text(cell_value(row, text_col - 1))
        amount_value = normalize_text(cell_value(row, amount_col - 1))
        if text_value.upper() in {IBP_SECTION_LABEL, "IBP FROM OTHER BRANCH", OTHER_PAYMENT_SECTION_LABEL}:
            break
        if _section_cell_is_empty(text_value) and _section_cell_is_empty(amount_value):
            return {"row_number": row_number, "values": row, "text_col": text_col, "amount_col": amount_col}
        row_number += 1
    return {"row_number": row_number, "values": [], "text_col": text_col, "amount_col": amount_col}


def find_first_section_posting_target(sheet_rows: list[list[Any]], section_labels: list[str], header_row: int) -> dict[str, Any] | None:
    for section_label in section_labels:
        target = find_section_posting_target(sheet_rows, section_label, header_row)
        if target:
            return target
    return None


def section_entry_exists(sheet_rows: list[list[Any]], section_label: str, header_row: int, text_value: str, amount_value: str) -> bool:
    section = find_section_row(sheet_rows, section_label, header_row)
    if not section:
        return False

    text_col = int(section["label_col"])
    amount_col = _section_amount_col(section["values"], text_col)
    row_number = int(section["row_number"]) + 1
    expected_text = normalize_text(text_value).upper()
    expected_amount = normalize_text(amount_value)
    while row_number <= len(sheet_rows):
        row = sheet_rows[row_number - 1]
        current_text = normalize_text(cell_value(row, text_col - 1))
        current_amount = normalize_text(cell_value(row, amount_col - 1))
        if current_text.upper() in {IBP_SECTION_LABEL, "IBP FROM OTHER BRANCH", OTHER_PAYMENT_SECTION_LABEL}:
            break
        if current_text.upper() == expected_text and current_amount == expected_amount:
            return True
        row_number += 1
    return False


def section_entry_exists_any(sheet_rows: list[list[Any]], section_labels: list[str], header_row: int, text_value: str, amount_value: str) -> bool:
    return any(section_entry_exists(sheet_rows, section_label, header_row, text_value, amount_value) for section_label in section_labels)


def is_duplicate_history_block(status: Any, issue: Any) -> bool:
    return normalize_text(status).upper() == "DUPLICATE" and normalize_text(issue) == "Duplicate transaction"


def account_row_has_reference(target_values: list[Any], header_map: dict[str, int], reference: Any, or_number: Any) -> bool:
    existing_ref = normalize_text(cell_value(target_values, header_map["REF"])).upper()
    reference_text = normalize_text(reference).upper()
    or_text = normalize_text(or_number)
    if not existing_ref:
        return False
    if reference_text and reference_text in existing_ref:
        return True
    return bool(or_text and re.search(rf"(?<!\d){re.escape(or_text)}(?!\d)", existing_ref))


def prepare_accounts_preview(parsed_df: pd.DataFrame, sheet_rows: list[list[Any]], headers: list[str], header_row: int) -> tuple[pd.DataFrame, list[str]]:
    try:
        header_map = build_header_map(headers, ACCOUNTS_HEADERS)
        account_index = build_account_index(sheet_rows, headers, header_row)
    except ValueError as exc:
        return pd.DataFrame(), [str(exc)]

    records = []
    for row in parsed_df.to_dict("records"):
        issue = row.get("Issue", "")
        status = row.get("Status", "PASSED")
        target = None
        posting_col = ""
        section_text_col = ""
        section_amount_col = ""
        if row.get("is_ibp"):
            ibp_text = f"{row.get('OR Number')} - {row.get('ibp_resolved_customer')}"
            ibp_amount = format_section_amount(row.get("Actual Collection", "0"))
            target = find_section_posting_target(sheet_rows, IBP_SECTION_LABEL, header_row)
            posting_col = "M"
            if is_duplicate_history_block(status, issue) and not section_entry_exists(sheet_rows, IBP_SECTION_LABEL, header_row, ibp_text, ibp_amount):
                status, issue = "PASSED", ""
            if status == "PASSED" and section_entry_exists(sheet_rows, IBP_SECTION_LABEL, header_row, ibp_text, ibp_amount):
                status, issue = "DUPLICATE", "IBP ACCOUNTS section entry already exists"
            if status == "PASSED" and not target:
                status, issue = "ERROR", "IBP section missing or full in target ACCOUNTS"
            if status == "PASSED" and not normalize_text(row.get("ibp_resolved_customer", "")):
                status, issue = "ERROR", "IBP customer details not resolved"
            if target:
                section_text_col = target.get("text_col", "")
                section_amount_col = target.get("amount_col", "")
        elif row.get("is_other_payment"):
            other_text = f"{row.get('OR Number')} - OTHER PAYMENT /{normalize_text(row.get('Account Name Only'))}"
            other_amount = format_section_amount(row.get("Actual Collection", "0"))
            target = find_first_section_posting_target(sheet_rows, OTHER_PAYMENT_SECTION_LABELS, header_row)
            posting_col = "OTHERS"
            if is_duplicate_history_block(status, issue) and not section_entry_exists_any(sheet_rows, OTHER_PAYMENT_SECTION_LABELS, header_row, other_text, other_amount):
                status, issue = "PASSED", ""
            if status == "PASSED" and section_entry_exists_any(sheet_rows, OTHER_PAYMENT_SECTION_LABELS, header_row, other_text, other_amount):
                status, issue = "DUPLICATE", "Other Payment ACCOUNTS section entry already exists"
            if status == "PASSED" and not target:
                status, issue = "ERROR", "OTHERS / OTHER PAYMENTS section missing or full in target ACCOUNTS"
            if target:
                section_text_col = target.get("text_col", "")
                section_amount_col = target.get("amount_col", "")
        else:
            target = account_index.get(normalize_text(row.get("Account Name")).upper())
            posting_col = classify_accounts(row.get("Reference", ""))
            if (
                target
                and is_duplicate_history_block(status, issue)
                and not account_row_has_reference(target["values"], header_map, row.get("Reference", ""), row.get("OR Number", ""))
            ):
                status, issue = "PASSED", ""
            if status == "PASSED" and not target:
                status, issue = "ERROR", "Account not found in ACCOUNTS"
            if status == "PASSED" and posting_col == "UNKNOWN":
                status, issue = "ERROR", "Unknown ACCOUNTS transaction type"
            if posting_col == NO_AMOUNT_COLUMN:
                posting_col = ""

        target_values = target["values"] if target else []
        records.append(
            {
                **row,
                "Target Tab": "ACCOUNTS",
                "Target Row": target["row_number"] if target else "",
                "Amount Column": posting_col,
                "Section Text Col": section_text_col,
                "Section Amount Col": section_amount_col,
                "IBP ACCOUNTS Entry": row.get("ibp_accounts_entry", ""),
                "Other Payment ACCOUNTS Entry": row.get("other_payment_accounts_entry", ""),
                "Existing DATE": cell_value(target_values, header_map["DATE"]) if target else "",
                "Existing REF": cell_value(target_values, header_map["REF"]) if target else "",
                "Existing OUTSTANDING BALANCE": cell_value(target_values, header_map["OUTSTANDING BALANCE"]) if target else "",
                "Target SIMSOFT LEDGER BALANCE": cell_value(target_values, header_map["OUTSTANDING BALANCE"]) if target else "",
                "Status": status,
                "Issue": issue,
            }
        )
    return pd.DataFrame(records), []


def decimal_to_display(value: Any) -> str:
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return normalize_text(value)


def format_section_amount(value: Any) -> str:
    amount = value if isinstance(value, Decimal) else parse_amount(value)
    return f"({amount:,.2f})"


def format_positive_section_amount(value: Any) -> str:
    amount = value if isinstance(value, Decimal) else parse_amount(value)
    return f"{amount:,.2f}"


def ibp_collecting_branch_name(value: Any) -> str:
    text = normalize_text(value)
    if "/" in text:
        text = text.split("/", 1)[-1]
    if "-" in text:
        text = text.split("-", 1)[-1]
    text = re.sub(r"\s+\d{1,2}(?:\.\d{1,2})?$", "", text)
    return normalize_text(text) or normalize_text(value)


def ibp_source_payment_reference(or_number: Any, collecting_branch_name: Any, particular: Any) -> str:
    return f"{normalize_text(or_number)} IBP {ibp_collecting_branch_name(collecting_branch_name)} - ({normalize_text(particular)})"


def normalize_ibp_particular(particular: Any) -> str:
    text = normalize_text(particular)
    if re.fullmatch(r"\d{1,2}(?:-\d{1,2})?", text):
        return f"{text}/36 MI"
    return text


def decimal_to_formula_term(value: Any) -> str:
    amount = value if isinstance(value, Decimal) else parse_amount(value)
    if amount == amount.to_integral_value():
        return str(int(amount))
    return f"{amount:.2f}"


def append_formula_terms(existing: Any, additions: list[Any]) -> str:
    terms = [decimal_to_formula_term(value) for value in additions if parse_amount(value) != Decimal("0.00")]
    existing_text = normalize_text(existing)
    if existing_text in {"", "-", "–", "—"}:
        return f"={'+'.join(terms)}" if terms else ""
    if existing_text.startswith("="):
        return existing_text + (f"+{'+'.join(terms)}" if terms else "")
    try:
        existing_term = decimal_to_formula_term(existing_text)
    except ValueError:
        existing_term = existing_text
    all_terms = [existing_term, *terms]
    return f"={'+'.join(term for term in all_terms if term)}"


def prepare_ibp_source_branch_updates(
    ibp_rows: pd.DataFrame,
    sheet_rows: list[list[Any]],
    headers: list[str],
    header_row: int,
    ibp_particulars: dict[str, str],
    collecting_branch_name: str,
    ibp_payment_breakdowns: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    header_map = build_header_map(headers, ACCOUNTS_HEADERS)
    account_index = build_account_index(sheet_rows, headers, header_row)
    updates: list[dict[str, Any]] = []
    working_rows: dict[int, list[Any]] = {}

    passed_rows = ibp_rows[ibp_rows["Status"] == "PASSED"] if "Status" in ibp_rows else pd.DataFrame()
    for row in passed_rows.to_dict("records"):
        if not row.get("is_ibp"):
            continue
        key = normalize_text(row.get("Transaction Key", ""))
        particular = normalize_ibp_particular(ibp_particulars.get(key, ""))
        if not particular:
            raise ValueError(f"IBP particular is required for OR {row.get('OR Number', '')}.")
        has_manual_breakdown = key in (ibp_payment_breakdowns or {})
        breakdown = (ibp_payment_breakdowns or {}).get(key, {})
        breakdown_rebate = normalize_text(breakdown.get("rebate", "")) if isinstance(breakdown, dict) else ""
        breakdown_amount = normalize_text(breakdown.get("amount", "")) if isinstance(breakdown, dict) else ""
        breakdown_penalty = normalize_text(breakdown.get("penalty", "")) if isinstance(breakdown, dict) else ""
        if has_manual_breakdown and not breakdown_amount:
            raise ValueError(f"IBP payment amount is required for OR {row.get('OR Number', '')}.")
        rebate_value = parse_amount(breakdown_rebate) if breakdown_rebate else parse_amount(row["Rebate"])
        amount_value = parse_amount(breakdown_amount) if breakdown_amount else parse_amount(row["Amount"])
        penalty_value = parse_amount(breakdown_penalty) if breakdown_penalty else parse_amount(row["Interest"])

        account_no = normalize_text(row.get("ibp_account_no", "")).upper()
        target = account_index.get(account_no)
        if not target:
            for candidate in account_index.values():
                account_value = normalize_text(cell_value(candidate["values"], header_map["ACCOUNT"]))
                candidate_account_no = normalize_text(account_value.split("/", 1)[0]).upper()
                if candidate_account_no == account_no:
                    target = candidate
                    break
        if not target:
            raise ValueError(f"IBP source account not found in source branch ACCOUNTS: {account_no}")

        payment_col = classify_accounts(particular)
        if payment_col == "UNKNOWN":
            raise ValueError(f"Unknown IBP particular for OR {row.get('OR Number', '')}: {particular}")
        if payment_col == NO_AMOUNT_COLUMN:
            payment_col = ""

        target_row = int(target["row_number"])
        if target_row not in working_rows:
            original = sheet_rows[target_row - 1] if target_row - 1 < len(sheet_rows) else []
            working_rows[target_row] = list(original)
        existing = working_rows[target_row]
        max_col = max(header_map.values())
        if len(existing) <= max_col:
            existing.extend([""] * (max_col + 1 - len(existing)))

        source_ref = ibp_source_payment_reference(row.get("OR Number", ""), collecting_branch_name, particular)
        source_row = row.copy()
        source_row["Amount Column"] = payment_col
        source_row["Amount"] = amount_value
        source_row["Rebate"] = rebate_value
        source_row["Interest"] = penalty_value
        existing[header_map["DATE"]] = append_unique_line_break(existing[header_map["DATE"]], display_sheet_date(row["Date"]))
        existing[header_map["REF"]] = append_line_break(existing[header_map["REF"]], source_ref)
        existing[header_map["REB"]] = sum_numeric_or_blank(existing[header_map["REB"]], rebate_value)
        if not is_no_amount_column(payment_col):
            existing[header_map[payment_col]] = append_formula_terms(existing[header_map[payment_col]], [amount_value])
        existing[header_map["PENALTY"]] = append_formula_terms(existing[header_map["PENALTY"]], [penalty_value])
        projected_ledger_balance = subtract_numeric(
            existing[header_map["OUTSTANDING BALANCE"]],
            accounts_ledger_deduction(source_row),
        )
        existing[header_map["SIMSOFT LEDGER BALANCE"]] = decimal_to_display(projected_ledger_balance)

        ibp_text = f"{row.get('OR Number')} - {row.get('ibp_resolved_customer')}"
        ibp_amount = format_positive_section_amount(row.get("Actual Collection", "0"))
        if section_entry_exists(sheet_rows, IBP_FROM_SECTION_LABEL, header_row, ibp_text, ibp_amount):
            continue
        section_target = find_section_posting_target(sheet_rows, IBP_FROM_SECTION_LABEL, header_row)
        if not section_target or not section_target.get("values"):
            raise ValueError("IBP FROM OTHER BRANCH section missing or full in source branch ACCOUNTS.")
        updates.extend(
            [
                {"row": int(section_target["row_number"]), "col": int(section_target["text_col"]), "value": ibp_text},
                {"row": int(section_target["row_number"]), "col": int(section_target["amount_col"]), "value": ibp_amount},
            ]
        )
        sheet_rows[int(section_target["row_number"]) - 1][int(section_target["text_col"]) - 1] = ibp_text
        sheet_rows[int(section_target["row_number"]) - 1][int(section_target["amount_col"]) - 1] = ibp_amount

    mutable_headers = ["DATE", "REF", "REB", "CASH", "DP", "CM", "CM TO M", "M", "PENALTY", "OTHERS", "REPO", "SIMSOFT LEDGER BALANCE", "STATUS", "DATE FULLY PAID"]
    for target_row, values in working_rows.items():
        for header in mutable_headers:
            if header in header_map:
                update = {"row": target_row, "col": header_map[header] + 1, "value": values[header_map[header]]}
                if header == "DATE":
                    update["value_input_option"] = "RAW"
                updates.append(update)
    return updates


def prepare_sheet_updates(preview_df: pd.DataFrame, sheet_rows: list[list[Any]], headers: list[str]) -> list[dict[str, Any]]:
    header_map = build_header_map(headers, ACCOUNTS_HEADERS)
    updates: list[dict[str, Any]] = []
    working_rows: dict[int, list[Any]] = {}

    for row in preview_df[preview_df["Status"] == "PASSED"].to_dict("records"):
        target_row = int(row["Target Row"])
        if row.get("is_ibp"):
            updates.extend(
                [
                    {"row": target_row, "col": int(row["Section Text Col"]), "value": f"{row['OR Number']} - {row['ibp_resolved_customer']}"},
                    {"row": target_row, "col": int(row["Section Amount Col"]), "value": format_section_amount(row["Actual Collection"])},
                ]
            )
            continue
        if row.get("is_other_payment"):
            updates.extend(
                [
                    {"row": target_row, "col": int(row["Section Text Col"]), "value": f"{row['OR Number']} - OTHER PAYMENT /{normalize_text(row['Account Name Only'])}"},
                    {"row": target_row, "col": int(row["Section Amount Col"]), "value": format_section_amount(row["Actual Collection"])},
                ]
            )
            continue

        if target_row not in working_rows:
            original = sheet_rows[target_row - 1] if target_row - 1 < len(sheet_rows) else []
            working_rows[target_row] = list(original)
        existing = working_rows[target_row]
        max_col = max(header_map.values())
        if len(existing) <= max_col:
            existing.extend([""] * (max_col + 1 - len(existing)))

        amount_col = row["Amount Column"]
        existing[header_map["DATE"]] = append_unique_line_break(existing[header_map["DATE"]], display_sheet_date(row["Date"]))
        existing[header_map["REF"]] = append_line_break(existing[header_map["REF"]], row["Reference"])
        existing[header_map["REB"]] = sum_numeric_or_blank(existing[header_map["REB"]], row["Rebate"])
        if not is_no_amount_column(amount_col):
            existing[header_map[amount_col]] = append_formula_terms(existing[header_map[amount_col]], [row["Amount"]])
        existing[header_map["PENALTY"]] = append_formula_terms(existing[header_map["PENALTY"]], [row["Interest"]])
        projected_ledger_balance = subtract_numeric(
            existing[header_map["OUTSTANDING BALANCE"]],
            accounts_ledger_deduction(row),
        )
        existing[header_map["SIMSOFT LEDGER BALANCE"]] = decimal_to_display(projected_ledger_balance)
        if (
            "STATUS" in header_map
            and "DATE FULLY PAID" in header_map
            and should_mark_fully_paid(row, projected_ledger_balance, existing[header_map["STATUS"]])
        ):
            existing[header_map["STATUS"]] = "FULLY PAID"
            existing[header_map["DATE FULLY PAID"]] = display_sheet_date(row["Date"])

    mutable_headers = ["DATE", "REF", "REB", "CASH", "DP", "CM", "CM TO M", "M", "PENALTY", "OTHERS", "REPO", "SIMSOFT LEDGER BALANCE", "STATUS", "DATE FULLY PAID"]
    for target_row, values in working_rows.items():
        for header in mutable_headers:
            if header in header_map:
                updates.append({"row": target_row, "col": header_map[header] + 1, "value": values[header_map[header]]})
    return updates


def find_daily_collection_cells(sheet_rows: list[list[Any]]) -> dict[str, tuple[int, int]]:
    date_cells: dict[str, tuple[int, int]] = {}
    for row_number, row in enumerate(sheet_rows, start=1):
        for zero_based_col, value in enumerate(row):
            text = normalize_text(value)
            if "-" not in text or len(text) > 12:
                continue
            try:
                iso_date = parse_date(text)
            except ValueError:
                continue
            date_cells[iso_date] = (row_number, zero_based_col + 2)
    return date_cells


def prepare_daily_collection_updates(preview_df: pd.DataFrame, sheet_rows: list[list[Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    updates: list[dict[str, Any]] = []
    errors: list[str] = []
    if "Status" in preview_df:
        account_section_duplicates = preview_df[
            (preview_df["Status"] == "DUPLICATE")
            & preview_df.get("Issue", pd.Series("", index=preview_df.index)).isin(
                ["IBP ACCOUNTS section entry already exists", "Other Payment ACCOUNTS section entry already exists"]
            )
        ]
        passed = pd.concat([preview_df[preview_df["Status"] == "PASSED"], account_section_duplicates], ignore_index=True)
    else:
        passed = pd.DataFrame()
    if passed.empty:
        return updates, errors

    date_cells = find_daily_collection_cells(sheet_rows)
    for date_value, group in passed.groupby("Date"):
        iso_date = normalize_text(date_value)
        if iso_date not in date_cells:
            errors.append(f"Daily collection date not found in ACCOUNTS date list: {iso_date}")
            continue
        row_number, amount_col = date_cells[iso_date]
        existing = cell_value(sheet_rows[row_number - 1], amount_col - 1)
        formula = append_formula_terms(existing, list(group["Actual Collection"]))
        updates.append({"row": row_number, "col": amount_col, "value": formula})
    return updates, errors
