from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from .google_sheets import fetch_worksheet_rows, row_headers
from .parser import normalize_text

IBP_REFERENCE_PATTERN = re.compile(r"^\s*(\d+)\s*-\s*\(\s*(MMC\d{3})-(\d+)\s*\)\s*$", re.IGNORECASE)
IBP_ACCOUNT_PATTERN = re.compile(r"^\s*(MMC\d{3})-(\d+)\s*$", re.IGNORECASE)
IBP_SECTION_LABEL = "IBP TO OTHER BRANCH"


def is_ibp_transaction(account_name: str, reference: str) -> bool:
    name = normalize_text(account_name).upper()
    return "IBP PAYMENTS" in name or bool(IBP_REFERENCE_PATTERN.match(normalize_text(reference)))


def parse_ibp_reference(reference: str) -> dict[str, str]:
    text = normalize_text(reference)
    match = IBP_REFERENCE_PATTERN.match(text)
    if not match:
        raise ValueError("Invalid IBP reference")
    return {
        "or_number": match.group(1),
        "ibp_account_no": f"{match.group(2).upper()}-{match.group(3)}",
        "ibp_source_branch_id": match.group(2).upper(),
        "ibp_account_id": match.group(3),
        "particulars": f"({match.group(2).upper()}-{match.group(3)})",
    }


def build_ibp_accounts_line(or_number: str, full_account_name: str) -> str:
    return f"{or_number} - {full_account_name}"


def format_ibp_accounts_amount(amount: Any) -> str:
    value = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    return f"({value:,.2f})"


def build_ibp_accounts_entry(or_number: str, full_account_name: str, amount: Any) -> str:
    return f"{build_ibp_accounts_line(or_number, full_account_name)}     {format_ibp_accounts_amount(amount)}"


def lookup_account_in_branch_sheet(spreadsheet_id: str, account_no: str, service_account_info: dict[str, Any]) -> dict[str, Any]:
    sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
    try:
        worksheet, rows = fetch_worksheet_rows(sheet_url, "ACCOUNTS", service_account_info)
    except Exception as exc:
        return {
            "status": "ERROR",
            "issue": f"ACCOUNTS tab missing in source branch sheet: {exc}",
            "resolved_customer": "",
        }
    try:
        headers = row_headers(rows, 3)
    except Exception as exc:
        return {
            "status": "ERROR",
            "issue": "ACCOUNTS tab missing in source branch sheet",
            "resolved_customer": "",
        }
    from .accounts import build_account_index, build_header_map, cell_value

    header_map = build_header_map(headers, ["ACCOUNT"])
    account_index = build_account_index(rows, headers, 3)
    account_key = normalize_text(account_no).upper()
    target = account_index.get(account_key)
    if not target:
        for candidate in account_index.values():
            account_value = normalize_text(cell_value(candidate["values"], header_map["ACCOUNT"]))
            candidate_account_no = normalize_text(account_value.split("/", 1)[0]).upper()
            if candidate_account_no == account_key:
                target = candidate
                break
    if not target:
        return {
            "status": "NEEDS REVIEW",
            "issue": "IBP customer account not found in source branch",
            "resolved_customer": "",
        }
    account_value = cell_value(target["values"], header_map["ACCOUNT"])
    return {
        "status": "OK",
        "issue": "",
        "resolved_customer": normalize_text(account_value),
    }


def build_branch_account_lookup(spreadsheet_id: str, service_account_info: dict[str, Any]) -> dict[str, Any]:
    sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
    worksheet, rows = fetch_worksheet_rows(sheet_url, "ACCOUNTS", service_account_info)
    headers = row_headers(rows, 3)

    from .accounts import build_account_index, build_header_map, cell_value

    header_map = build_header_map(headers, ["ACCOUNT"])
    account_index = build_account_index(rows, headers, 3)
    by_exact_name = {normalize_text(key).upper(): value for key, value in account_index.items()}
    by_account_no: dict[str, dict[str, Any]] = {}
    for candidate in account_index.values():
        account_value = normalize_text(cell_value(candidate["values"], header_map["ACCOUNT"]))
        candidate_account_no = normalize_text(account_value.split("/", 1)[0]).upper()
        if candidate_account_no:
            by_account_no[candidate_account_no] = candidate
    return {"rows": rows, "header_map": header_map, "by_exact_name": by_exact_name, "by_account_no": by_account_no}


def lookup_account_in_cached_branch(
    spreadsheet_id: str,
    account_no: str,
    service_account_info: dict[str, Any],
    branch_account_index_cache: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    try:
        branch_lookup = branch_account_index_cache.get(spreadsheet_id)
        if branch_lookup is None:
            branch_lookup = build_branch_account_lookup(spreadsheet_id, service_account_info)
            branch_account_index_cache[spreadsheet_id] = branch_lookup
    except Exception as exc:
        return {
            "status": "ERROR",
            "issue": f"ACCOUNTS tab missing in source branch sheet: {exc}",
            "resolved_customer": "",
        }

    from .accounts import cell_value

    account_key = normalize_text(account_no).upper()
    target = branch_lookup["by_exact_name"].get(account_key) or branch_lookup["by_account_no"].get(account_key)
    if not target:
        return {
            "status": "NEEDS REVIEW",
            "issue": "IBP customer account not found in source branch",
            "resolved_customer": "",
        }
    account_value = cell_value(target["values"], branch_lookup["header_map"]["ACCOUNT"])
    return {
        "status": "OK",
        "issue": "",
        "resolved_customer": normalize_text(account_value),
    }


def resolve_ibp_customer(
    account_no: str,
    branch_index: dict[str, dict[str, Any]],
    service_account_info: dict[str, Any],
    account_lookup_cache: dict[str, dict[str, Any]] | None = None,
    branch_account_index_cache: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    branch_id = normalize_text(account_no).split("-", 1)[0].upper()
    branch_sheet = branch_index.get(branch_id)
    if not branch_sheet:
        return {
            "status": "ERROR",
            "issue": f"Branch sheet not found for {branch_id}",
            "resolved_customer": "",
        }
    if branch_sheet.get("status") == "MULTIPLE_MATCHES":
        return {
            "status": "ERROR",
            "issue": f"Multiple branch sheets found for {branch_id}; remove duplicates or rename the files.",
            "resolved_customer": "",
        }
    cache_key = f"{branch_sheet['spreadsheet_id']}|{normalize_text(account_no).upper()}"
    if account_lookup_cache is not None and cache_key in account_lookup_cache:
        return account_lookup_cache[cache_key]
    if branch_account_index_cache is not None:
        result = lookup_account_in_cached_branch(branch_sheet["spreadsheet_id"], account_no, service_account_info, branch_account_index_cache)
    else:
        result = lookup_account_in_branch_sheet(branch_sheet["spreadsheet_id"], account_no, service_account_info)
    if account_lookup_cache is not None:
        account_lookup_cache[cache_key] = result
    return result


def annotate_ibp_rows(
    parsed_df: Any,
    branch_index: dict[str, dict[str, Any]],
    service_account_info: dict[str, Any],
    account_lookup_cache: dict[str, dict[str, Any]] | None = None,
    branch_account_index_cache: dict[str, dict[str, Any]] | None = None,
) -> Any:
    records: list[dict[str, Any]] = []
    effective_lookup_cache = account_lookup_cache if account_lookup_cache is not None else {}
    effective_branch_cache = branch_account_index_cache if branch_account_index_cache is not None else {}
    for row in parsed_df.to_dict("records"):
        row_data = dict(row)
        row_data["is_ibp"] = is_ibp_transaction(row_data.get("Account Name", ""), row_data.get("Reference", ""))
        row_data.setdefault("ibp_lookup_status", "")
        row_data.setdefault("ibp_resolved_customer", "")
        row_data.setdefault("ibp_account_no", "")
        row_data.setdefault("ibp_source_branch_id", "")
        row_data.setdefault("ibp_account_id", "")
        if row_data["is_ibp"]:
            try:
                parsed = parse_ibp_reference(row_data.get("Reference", ""))
                row_data["ibp_account_no"] = parsed["ibp_account_no"]
                row_data["ibp_source_branch_id"] = parsed["ibp_source_branch_id"]
                row_data["ibp_account_id"] = parsed["ibp_account_id"]
            except ValueError as exc:
                row_data["Status"] = "ERROR"
                row_data["Issue"] = "; ".join(filter(None, [row_data.get("Issue", ""), str(exc)]))
            else:
                if row_data.get("Status") == "PASSED":
                    if not branch_index:
                        row_data["Status"] = "ERROR"
                        row_data["Issue"] = "; ".join(filter(None, [row_data.get("Issue", ""), "Branch folder scan is required for IBP resolution"]))
                        row_data["ibp_lookup_status"] = "ERROR"
                    else:
                        resolution = resolve_ibp_customer(
                            row_data["ibp_account_no"],
                            branch_index,
                            service_account_info,
                            effective_lookup_cache,
                            effective_branch_cache,
                        )
                        row_data["ibp_lookup_status"] = resolution.get("status", "")
                        row_data["ibp_resolved_customer"] = resolution.get("resolved_customer", "")
                        if resolution.get("status") != "OK":
                            row_data["Status"] = "ERROR"
                            row_data["Issue"] = "; ".join(filter(None, [row_data.get("Issue", ""), resolution.get("issue", "")]))
                        else:
                            row_data["ibp_accounts_entry"] = build_ibp_accounts_entry(
                                row_data.get("OR Number", parsed["or_number"]),
                                row_data["ibp_resolved_customer"],
                                row_data.get("Actual Collection", row_data.get("Amount", "0")),
                            )
        records.append(row_data)
    return parsed_df.__class__(records)
