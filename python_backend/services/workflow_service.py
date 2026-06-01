from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd

from core.accounts import build_fully_paid_cash_export, build_header_map, cell_value, decimal_to_display, display_sheet_date, prepare_accounts_preview, prepare_daily_collection_updates, prepare_ibp_source_branch_updates, prepare_sheet_updates
from core.ai_resolver import build_ai_resolver_context, resolve_posting_with_gemini
from core.audit import new_batch_id
from core.branch_folder_lookup import build_branch_index, extract_drive_folder_id, scan_branch_folder, scan_branch_folder_metadata
from core.concurrency import (
    BranchLock,
    BranchLockError,
    DuplicateAuditStore,
    LocalCsvDuplicateAuditStore,
    branch_lock_key,
    iso_now,
)
from core.daily_report import daily_column_map, daily_tab_name, prepare_daily_preview, prepare_daily_sheet_updates
from core.google_sheets import AUTH_MODE_SERVICE_ACCOUNT, extract_spreadsheet_id, get_gspread_client, load_service_account_json, row_headers
from core.ibp_resolver import IBP_SECTION_LABEL
from core.ibp_resolver import annotate_ibp_rows
from core.other_payment import OTHER_PAYMENT_SECTION_LABEL
from core.other_payment import annotate_other_payment_rows
from core.parser import normalize_text, read_simsoft_excel
from core.receipt import find_receipt_blocks, prepare_receipt_preview, prepare_receipt_updates, receipt_block_start
from core.scr_vs_br import RECEIPT_BLOCKS, SCR_TAB, find_scr_date_rows, prepare_scr_vs_br_updates
from core.settings import ENABLE_LIVE_POSTING
from core.validation import calculate_summary, can_swipe_to_post, parse_and_validate_simsoft
from python_backend.models.app_state import AppState, GoogleSheetState, PostingState
from python_backend.application.events import ApplicationEvent, EventBus, InMemoryEventBus
from python_backend.application.ports import (
    AuditRepository,
    DefaultGoogleSheetsGateway,
    GoogleSheetsGateway,
    LocalCsvAuditRepository,
    PostingTransactionManager,
)

TARGET_TAB = "ACCOUNTS"
ACCOUNTS_HEADER_ROW = 3
RECEIPT_TAB = "RECEIPT"
RECEIPT_TAB_ALIASES = ["RECEIPT", "RECIEPT"]
RECEIPT_HEADER_ROW = 1
DAILY_TAB = "1-31"
LOCAL_SERVICE_ACCOUNT_PATH = Path(os.getenv("SIMSOFT_SERVICE_ACCOUNT_JSON_PATH", "config/service_account.json"))
FOLDER_SCAN_CACHE_PATH = Path("data/cache/branch_index.json")
FOLDER_SCAN_CACHE_TTL_SECONDS = 12 * 60 * 60


def unique_messages(messages: list[str]) -> list[str]:
    return list(dict.fromkeys(message for message in messages if message))


def sheet_id_from_url(sheet_url: str) -> str:
    try:
        return extract_spreadsheet_id(sheet_url)
    except ValueError:
        return ""


def daily_tab_aliases(tab_name: str) -> list[str]:
    return list(dict.fromkeys([tab_name, tab_name.strip(), tab_name.replace("-", "\u2013"), tab_name.replace("-", "\u2014")]))


def daily_tab_for_parsed_rows(parsed_df: pd.DataFrame) -> tuple[str, list[str]]:
    if parsed_df.empty or "Date" not in parsed_df:
        return DAILY_TAB, []
    dates = pd.to_datetime(parsed_df["Date"], errors="coerce").dropna()
    if dates.empty:
        return DAILY_TAB, []
    months = dates.dt.to_period("M").unique()
    errors = []
    if len(months) > 1:
        errors.append("SIMSOFT file contains multiple months. Upload one branch/month export at a time.")
    return daily_tab_name(dates.iloc[0].date()), errors


def friendly_google_error(exc: Exception, service_account_email: str, sheet_url: str, tab_name: str = TARGET_TAB) -> str:
    cause = getattr(exc, "__cause__", None)
    message = str(cause or exc).strip() or exc.__class__.__name__
    if "WorksheetNotFound" in exc.__class__.__name__ or "worksheet" in message.lower():
        return f"The tab named {tab_name} was not found. Check the spreadsheet tab name."
    if "429" in message or "Quota exceeded" in message:
        return (
            f"Google Sheets read quota was temporarily exceeded while loading {tab_name}. "
            "Wait about 60 seconds, then click Refresh Google Sheet Data. The app caches reads to avoid repeating this."
        )
    disabled_markers = [
        "Google Sheets API has not been used",
        "accessNotConfigured",
        "serviceDisabled",
        "SERVICE_DISABLED",
    ]
    if any(marker in message for marker in disabled_markers):
        return (
            "Google Sheets API is disabled for this service account project. Open Google Cloud Console, "
            "enable Google Sheets API for project dulcet-velocity-495608-n9, wait a few minutes, then refresh this app."
        )
    if "Google Drive API has not been used" in message or "drive.googleapis.com" in message:
        return (
            "Google Drive API is disabled for this service account project. Open Google Cloud Console, "
            "enable Google Drive API for project dulcet-velocity-495608-n9, wait a few minutes, then refresh this app."
        )
    if exc.__class__.__name__ == "PermissionError":
        sheet_id = sheet_id_from_url(sheet_url) or "unknown"
        return (
            "Google Sheet access is blocked. Share the exact spreadsheet as Editor with "
            f"{service_account_email}. Current Sheet ID: {sheet_id}"
        )
    return message


def fetch_first_available_tab_with_fetcher(fetcher: Any, tab_names: list[str]) -> tuple[Any, list[list[Any]], str]:
    last_error: Exception | None = None
    for tab_name in tab_names:
        try:
            worksheet, rows = fetcher(tab_name)
            return worksheet, rows, tab_name
        except Exception as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def load_service_account_context(path: Path = LOCAL_SERVICE_ACCOUNT_PATH) -> tuple[dict[str, Any], str]:
    with path.open("rb") as fh:
        service_account_info = load_service_account_json(fh)
    return service_account_info, service_account_info.get("client_email", "")


def scan_drive_folder(auth_context: Any, folder_url: str) -> dict[str, dict[str, Any]]:
    folder_id = extract_drive_folder_id(folder_url)
    return scan_branch_folder(auth_context, folder_id)


def file_cache_key(file_path: Path | None) -> str:
    if file_path is None:
        return ""
    stat = file_path.stat()
    return f"{file_path.resolve()}|{stat.st_mtime_ns}|{stat.st_size}"


def files_cache_key(file_paths: list[Path]) -> str:
    return "||".join(file_cache_key(file_path) for file_path in file_paths)


def branch_index_signature(branch_index: dict[str, dict[str, Any]]) -> tuple[tuple[str, str, str, str], ...]:
    return tuple(
        sorted(
            (
                branch_id,
                info.get("spreadsheet_id", ""),
                info.get("branch_name", ""),
                info.get("status", ""),
            )
            for branch_id, info in branch_index.items()
        )
    )


def duplicate_branch_warnings(branch_index: dict[str, dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    for branch_id, info in sorted(branch_index.items()):
        if info.get("status") != "MULTIPLE_MATCHES":
            continue
        names = info.get("matching_file_names") or [item.get("file_name", "") for item in info.get("matching_files", [])]
        warnings.append(f"{branch_id} has multiple matching files: {', '.join(name for name in names if name)}")
    return warnings


def preview_issue_summary(tab_name: str, df: pd.DataFrame, limit: int = 2) -> list[str]:
    if df.empty or "Status" not in df:
        return []
    problem_rows = df[df["Status"].isin(["ERROR", "DUPLICATE"])]
    if problem_rows.empty:
        return []
    summaries: list[str] = []
    for row in problem_rows.head(limit).to_dict("records"):
        issue = str(row.get("Issue", "")).strip() or str(row.get("Status", "")).strip()
        account = str(row.get("Account Name", "") or row.get("Account", "")).strip()
        if account:
            summaries.append(f"{tab_name}: {account} - {issue}")
        else:
            summaries.append(f"{tab_name}: {issue}")
    remaining = len(problem_rows) - len(summaries)
    if remaining > 0:
        summaries.append(f"{tab_name}: +{remaining} more issue(s)")
    return summaries


def preview_problem_rows(df: pd.DataFrame, postable_keys: set[str] | None = None) -> pd.DataFrame:
    if df.empty or "Status" not in df:
        return pd.DataFrame()
    problems = df[df["Status"] == "ERROR"]
    if postable_keys is None or "Transaction Key" not in problems:
        return problems
    keys = problems["Transaction Key"].astype(str)
    return problems[(keys == "") | keys.isin(postable_keys)]


def preview_has_blocking_errors(df: pd.DataFrame, postable_keys: set[str] | None = None) -> bool:
    return not preview_problem_rows(df, postable_keys).empty


def accounts_missing_from_target_branch(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "Issue" not in df:
        return pd.DataFrame()
    issues = df["Issue"].astype(str)
    return df[(df.get("Status", "") == "ERROR") & issues.str.contains("Account not found in ACCOUNTS", case=False, na=False)]


def rows_for_different_branch(parsed_df: pd.DataFrame, target_branch_id: str) -> pd.DataFrame:
    if parsed_df.empty or "Account Number" not in parsed_df or not target_branch_id:
        return pd.DataFrame()
    target = normalize_text(target_branch_id).upper()

    def account_branch(value: Any) -> str:
        account_number = normalize_text(value).upper()
        if "-" not in account_number:
            return ""
        return account_number.split("-", 1)[0]

    branches = parsed_df["Account Number"].map(account_branch)
    return parsed_df[(branches != "") & (branches != target)]


def preview_blocking_issue_summary(tab_name: str, df: pd.DataFrame, postable_keys: set[str] | None = None, limit: int = 2) -> list[str]:
    problem_rows = preview_problem_rows(df, postable_keys)
    if problem_rows.empty:
        return []
    summaries: list[str] = []
    for row in problem_rows.head(limit).to_dict("records"):
        issue = str(row.get("Issue", "")).strip() or str(row.get("Status", "")).strip()
        account = str(row.get("Account Name", "") or row.get("Account", "")).strip()
        if account:
            summaries.append(f"{tab_name}: {account} - {issue}")
        else:
            summaries.append(f"{tab_name}: {issue}")
    remaining = len(problem_rows) - len(summaries)
    if remaining > 0:
        summaries.append(f"{tab_name}: +{remaining} more issue(s)")
    return summaries


ACCOUNTS_ALREADY_POSTED_ISSUES = {
    "IBP ACCOUNTS section entry already exists",
    "Other Payment ACCOUNTS section entry already exists",
}


def accounts_duplicate_is_postable_elsewhere(row: pd.Series | dict[str, Any]) -> bool:
    return (
        str(row.get("Status", "")).upper() == "DUPLICATE"
        and str(row.get("Issue", "")).strip() in ACCOUNTS_ALREADY_POSTED_ISSUES
    )


def passed_transaction_keys(df: pd.DataFrame) -> set[str]:
    if df.empty or not {"Status", "Transaction Key"}.issubset(df.columns):
        return set()
    status = df["Status"].astype(str)
    issue = df["Issue"].astype(str).str.strip() if "Issue" in df.columns else pd.Series("", index=df.index)
    eligible = df[
        (status == "PASSED")
        | ((status.str.upper() == "DUPLICATE") & issue.isin(ACCOUNTS_ALREADY_POSTED_ISSUES))
    ]
    return {
        str(key)
        for key in eligible["Transaction Key"].tolist()
        if key
    }


def filter_preview_to_transaction_keys(df: pd.DataFrame, transaction_keys: set[str]) -> pd.DataFrame:
    if df.empty or "Transaction Key" not in df:
        return df
    keys = df["Transaction Key"].astype(str)
    return df[(keys == "") | keys.isin(transaction_keys)].copy()


def sheet_layout_with_updates(rows: list[list[Any]], updates: list[dict[str, Any]], max_rows: int = 220, max_cols: int = 28) -> dict[str, Any]:
    grid = [list(row[:max_cols]) for row in rows[:max_rows]]
    updated_cells: list[dict[str, Any]] = []
    for update in updates:
        try:
            row_number = int(update["row"])
            col_number = int(update["col"])
        except Exception:
            continue
        if row_number < 1 or col_number < 1 or row_number > max_rows or col_number > max_cols:
            continue
        while len(grid) < row_number:
            grid.append([])
        while len(grid[row_number - 1]) < col_number:
            grid[row_number - 1].append("")
        previous_value = grid[row_number - 1][col_number - 1]
        value = update.get("value", "")
        grid[row_number - 1][col_number - 1] = value
        updated_cells.append(
            {
                "row": row_number,
                "col": col_number,
                "previousValue": previous_value,
                "value": value,
            }
        )
    return {
        "rows": grid,
        "updatedCells": updated_cells,
    }


def projected_sheet_layout(rows: list[list[Any]], row_numbers: list[int], col_numbers: list[int], updates: list[dict[str, Any]]) -> dict[str, Any]:
    ordered_rows = [row for row in dict.fromkeys(row_numbers) if row >= 1]
    ordered_cols = [col for col in dict.fromkeys(col_numbers) if col >= 1]
    if not ordered_rows or not ordered_cols:
        return {"rows": [], "updatedCells": []}

    row_position = {row_number: index + 1 for index, row_number in enumerate(ordered_rows)}
    col_position = {col_number: index + 1 for index, col_number in enumerate(ordered_cols)}
    grid: list[list[Any]] = []
    for row_number in ordered_rows:
        source = rows[row_number - 1] if row_number - 1 < len(rows) else []
        grid.append([source[col_number - 1] if col_number - 1 < len(source) else "" for col_number in ordered_cols])

    updated_cells: list[dict[str, Any]] = []
    for update in updates:
        try:
            original_row = int(update["row"])
            original_col = int(update["col"])
        except Exception:
            continue
        if original_row not in row_position or original_col not in col_position:
            continue
        preview_row = row_position[original_row]
        preview_col = col_position[original_col]
        previous_value = grid[preview_row - 1][preview_col - 1]
        value = update.get("value", "")
        grid[preview_row - 1][preview_col - 1] = value
        updated_cells.append(
            {
                "row": preview_row,
                "col": preview_col,
                "sourceRow": original_row,
                "sourceCol": original_col,
                "previousValue": previous_value,
                "value": value,
            }
        )
    return {"rows": grid, "updatedCells": updated_cells}


def _update_rows(updates: list[dict[str, Any]]) -> list[int]:
    rows: list[int] = []
    for update in updates:
        try:
            rows.append(int(update["row"]))
        except Exception:
            continue
    return rows


def _update_cols(updates: list[dict[str, Any]]) -> list[int]:
    cols: list[int] = []
    for update in updates:
        try:
            cols.append(int(update["col"]))
        except Exception:
            continue
    return cols


def _accounts_section_context_rows(rows: list[list[Any]], preview_df: pd.DataFrame) -> list[int]:
    if preview_df.empty or not {"Target Row", "Section Text Col"}.issubset(preview_df.columns):
        return []
    section_labels = {IBP_SECTION_LABEL, "IBP FROM OTHER BRANCH", OTHER_PAYMENT_SECTION_LABEL, "OTHER PAYMENT", "OTHER PAYMENTS"}
    context_rows: list[int] = []
    for row in preview_df.to_dict("records"):
        try:
            target_row = int(row.get("Target Row") or 0)
            text_col = int(row.get("Section Text Col") or 0)
        except Exception:
            continue
        if target_row <= ACCOUNTS_HEADER_ROW or text_col < 1:
            continue
        for row_number in range(target_row - 1, ACCOUNTS_HEADER_ROW, -1):
            source = rows[row_number - 1] if row_number - 1 < len(rows) else []
            label = normalize_text(cell_value(source, text_col - 1)).upper()
            if label in section_labels:
                context_rows.extend(range(row_number, target_row + 1))
                break
    return context_rows


def accounts_layout_preview(state: AppState, updates: list[dict[str, Any]]) -> dict[str, Any]:
    sheet = state.sheet
    posting = state.posting
    try:
        header_map = build_header_map(sheet.accounts_headers)
    except Exception:
        return sheet_layout_with_updates(sheet.accounts_rows, updates, max_rows=80, max_cols=14)
    requested_headers = [
        "ACCOUNT",
        "DATE",
        "REF",
        "CASH",
        "DP",
        "CM",
        "CM TO M",
        "REB",
        "M",
        "PENALTY",
        "OTHERS",
        "OUTSTANDING BALANCE",
        "SIMSOFT LEDGER BALANCE",
    ]
    col_numbers = [header_map[header] + 1 for header in requested_headers if header in header_map]
    row_numbers = [ACCOUNTS_HEADER_ROW]
    if not posting.accounts_preview_df.empty and "Target Row" in posting.accounts_preview_df:
        for value in posting.accounts_preview_df["Target Row"].tolist():
            try:
                row_number = int(value)
            except Exception:
                continue
            if row_number > 0:
                row_numbers.append(row_number)
    row_numbers.extend(_accounts_section_context_rows(sheet.accounts_rows, posting.accounts_preview_df))
    row_numbers.extend(_update_rows(updates))
    return projected_sheet_layout(sheet.accounts_rows, sorted(set(row_numbers)), col_numbers, updates)


def daily_layout_preview(state: AppState, updates: list[dict[str, Any]]) -> dict[str, Any]:
    rows = state.sheet.daily_rows
    columns = daily_column_map(rows)
    requested = ["DATE", "OR", "ACCOUNT #", "ACCOUNT NAME", "PARTICULARS", "CASH", "DP", "MI", "REBATE", "PEN", "CM", "IBP", "OTHERS", "TOTAL"]
    col_numbers = [columns[column] for column in requested if column in columns]
    header_row = 1
    for index, row in enumerate(rows[:10], start=1):
        labels = {normalize_text(value).upper().replace(" ", "") for value in row}
        if {"DATE", "OR"}.issubset(labels) or "ACCOUNT#" in labels:
            header_row = index
            break
    row_numbers = [header_row, *_update_rows(updates)]
    return projected_sheet_layout(rows, sorted(set(row_numbers)), col_numbers, updates)


def _scr_row_has_or_context(row: list[Any]) -> bool:
    for block in RECEIPT_BLOCKS:
        for col_key in ("from_col", "to_col"):
            value = normalize_text(cell_value(row, int(block[col_key]) - 1))
            if value and value not in {"-", "â€“", "â€”"}:
                return True
    return False


def _scr_previous_context_rows(rows: list[list[Any]], update_rows: list[int], days: int = 7) -> list[int]:
    if not update_rows:
        return []
    date_rows_by_iso = find_scr_date_rows(rows)
    iso_by_row = {row_number: iso_date for iso_date, row_number in date_rows_by_iso.items()}
    context_rows: list[int] = []
    for target_row in update_rows:
        target_iso = iso_by_row.get(target_row)
        if not target_iso:
            continue
        try:
            target_date = date.fromisoformat(target_iso)
        except ValueError:
            continue
        for day_offset in range(days, 0, -1):
            candidate_iso = (target_date - timedelta(days=day_offset)).isoformat()
            candidate_row = date_rows_by_iso.get(candidate_iso)
            if not candidate_row:
                continue
            source = rows[candidate_row - 1] if candidate_row - 1 < len(rows) else []
            if _scr_row_has_or_context(source):
                context_rows.append(candidate_row)
    return context_rows


def _scr_header_row(rows: list[list[Any]]) -> int:
    for row_number, row in enumerate(rows, start=1):
        if normalize_text(cell_value(row, 0)).upper() == "SCR DATE":
            return row_number
    return 1


def receipt_layout_preview(state: AppState, updates: list[dict[str, Any]]) -> dict[str, Any]:
    rows = state.sheet.receipt_rows
    posting = state.posting
    if not updates and posting.receipt_preview_df.empty:
        return sheet_layout_with_updates(rows, updates, max_rows=80, max_cols=4)

    blocks = find_receipt_blocks(rows)
    actual_series = {
        normalize_text(value)
        for value in posting.parsed_df["OR Number"].tolist()
        if not posting.parsed_df.empty and "OR Number" in posting.parsed_df
    }
    actual_numeric_series = {
        int(series)
        for series in actual_series
        if series.isdigit()
    }

    physical_by_series: dict[int, dict[str, Any]] = {}
    physical_block_by_start: dict[int, dict[str, int]] = {}
    physical_group_start_by_series: dict[int, int] = {}
    row_group_start_by_row: dict[int, int] = {}
    sorted_blocks = sorted(blocks, key=lambda item: (item["header_row_index"], item["type_col"]))
    for block in sorted_blocks:
        header_row = int(block["header_row_index"]) + 1
        next_same_column_header = next(
            (
                int(candidate["header_row_index"]) + 1
                for candidate in sorted_blocks
                if int(candidate["type_col"]) == int(block["type_col"])
                and int(candidate["header_row_index"]) > int(block["header_row_index"])
            ),
            len(rows) + 1,
        )
        block_entries: list[tuple[int, int, dict[str, Any]]] = []
        for row_number in range(header_row + 1, next_same_column_header):
            row = rows[row_number - 1] if row_number - 1 < len(rows) else []
            series = normalize_text(cell_value(row, int(block["series_col"])))
            if not series.isdigit():
                continue
            series_number = int(series)
            block_entries.append(
                (
                    row_number,
                    series_number,
                    {
                        "type": cell_value(row, int(block["type_col"])),
                        "series": cell_value(row, int(block["series_col"])),
                        "date": cell_value(row, int(block["date_col"])),
                        "amount": cell_value(row, int(block["amount_col"])),
                    },
                )
            )
        if not block_entries:
            continue
        block_start = min(series for _, series, _ in block_entries)
        physical_block_by_start.setdefault(block_start, block)
        for row_number in range(header_row + 1, next_same_column_header):
            row_group_start_by_row[row_number] = block_start
        for _, series_number, physical in block_entries:
            physical_group_start_by_series[series_number] = block_start
            physical_by_series[series_number] = physical

    planned_by_series: dict[int, dict[str, Any]] = {}
    if not posting.receipt_preview_df.empty and "Series" in posting.receipt_preview_df:
        for row in posting.receipt_preview_df.to_dict("records"):
            series = normalize_text(row.get("Series", ""))
            if not series.isdigit() or str(row.get("Status", "")).upper() != "PASSED":
                continue
            series_number = int(series)
            current = planned_by_series.get(series_number)
            is_actual = series_number in actual_numeric_series
            if current and current.get("kind") == "actual" and not is_actual:
                continue
            planned_by_series[series_number] = {
                "type": row.get("Type", "CR") or "CR",
                "series": series,
                "date": display_sheet_date(row.get("Date")),
                "amount": decimal_to_display(row.get("Amount")),
                "kind": "actual" if is_actual else "cancelled",
                "targetRow": row.get("Target Row", ""),
            }

    def receipt_preview_block_start(series_number: int) -> int:
        planned = planned_by_series.get(series_number, {})
        try:
            target_row = int(planned.get("targetRow") or 0)
        except Exception:
            target_row = 0
        return (
            physical_group_start_by_series.get(series_number)
            or row_group_start_by_row.get(target_row)
            or receipt_block_start(series_number)
        )

    selected_source_series = actual_numeric_series or set(planned_by_series.keys())
    selected_starts = sorted({receipt_preview_block_start(series) for series in selected_source_series})
    if not selected_starts:
        return sheet_layout_with_updates(rows, updates, max_rows=80, max_cols=4)

    row_count = 53
    rows_by_block: list[list[list[Any]]] = []
    updates_by_block: list[list[dict[str, Any]]] = []
    for block_start in selected_starts:
        block = physical_block_by_start.get(block_start) or (sorted_blocks[0] if sorted_blocks else None)
        block_rows = [["", "", "", ""] for _ in range(row_count)]
        block_updates: list[dict[str, Any]] = []

        if block is not None:
            header_row = int(block["header_row_index"]) + 1
            source_title = rows[header_row - 3] if header_row >= 3 and header_row - 3 < len(rows) else []
            source_release = rows[header_row - 2] if header_row >= 2 and header_row - 2 < len(rows) else []
            source_header = rows[header_row - 1] if header_row - 1 < len(rows) else []
            block_rows[0] = [cell_value(source_title, int(block["type_col"]) + offset) for offset in range(4)]
            block_rows[1] = [cell_value(source_release, int(block["type_col"]) + offset) for offset in range(4)]
            block_rows[2] = [cell_value(source_header, int(block["type_col"]) + offset) for offset in range(4)]

        if not any(normalize_text(value) for value in block_rows[0]):
            block_rows[0] = ["BRANCH COLLECTION / NO RECEIPT", "", "", ""]
        if not any(normalize_text(value) for value in block_rows[1]):
            block_rows[1] = ["RELEASED", "", "RETURNED", ""]
        if not any(normalize_text(value) for value in block_rows[2]):
            block_rows[2] = ["TYPE", "SERIES", "DATE", "AMOUNT"]

        for offset, series_number in enumerate(range(block_start, block_start + 50), start=3):
            physical = physical_by_series.get(series_number, {})
            block_rows[offset] = [
                physical.get("type", ""),
                physical.get("series", series_number),
                physical.get("date", ""),
                physical.get("amount", ""),
            ]
            planned = planned_by_series.get(series_number)
            if not planned:
                continue
            block_rows[offset] = [planned["type"], planned["series"], planned["date"], planned["amount"]]
            for col_index in range(1, 5):
                block_updates.append(
                    {
                        "row": offset + 1,
                        "col": col_index,
                        "kind": planned["kind"],
                        "previousValue": "",
                        "value": block_rows[offset][col_index - 1],
                    }
                )

        rows_by_block.append(block_rows)
        updates_by_block.append(block_updates)

    grid: list[list[Any]] = []
    updated_cells: list[dict[str, Any]] = []
    for row_index in range(row_count):
        output_row: list[Any] = []
        for block_index, block_rows in enumerate(rows_by_block):
            if block_index > 0:
                output_row.append("")
            output_row.extend(block_rows[row_index])
        grid.append(output_row)

    for block_index, block_updates in enumerate(updates_by_block):
        col_offset = block_index * 5
        for cell in block_updates:
            updated_cells.append({**cell, "col": int(cell["col"]) + col_offset})

    return {"rows": grid, "updatedCells": updated_cells}


def scr_layout_preview(state: AppState, updates: list[dict[str, Any]]) -> dict[str, Any]:
    rows = state.sheet.scr_rows
    update_rows = _update_rows(updates)
    max_update_col = max(_update_cols(updates) or [14])
    col_numbers = list(range(1, max(14, max_update_col) + 1))
    row_numbers = {_scr_header_row(rows)}
    if update_rows:
        row_numbers.update(_scr_previous_context_rows(rows, update_rows))
        row_numbers.update(update_rows)
    else:
        date_rows = find_scr_date_rows(rows)
        if date_rows:
            first_date_row = min(date_rows.values())
            row_numbers.update(range(first_date_row, min(len(rows), first_date_row + 6) + 1))
    return projected_sheet_layout(rows, sorted(row_numbers), col_numbers, updates)


def build_sheet_layout_previews(state: AppState) -> dict[str, Any]:
    posting = state.posting
    sheet = state.sheet
    if posting.parsed_df.empty or not sheet.google_ready:
        return {}

    account_updates: list[dict[str, Any]] = []
    daily_collection_updates: list[dict[str, Any]] = []
    receipt_updates: list[dict[str, Any]] = []
    daily_sheet_updates: list[dict[str, Any]] = []
    try:
        account_updates = prepare_sheet_updates(posting.accounts_preview_df, sheet.accounts_rows, sheet.accounts_headers)
        daily_collection_updates, _ = prepare_daily_collection_updates(posting.accounts_preview_df, sheet.accounts_rows)
    except Exception:
        account_updates = []
        daily_collection_updates = []
    try:
        receipt_updates = prepare_receipt_updates(posting.receipt_preview_df, sheet.receipt_headers)
    except Exception:
        receipt_updates = []
    try:
        daily_sheet_updates, _ = prepare_daily_sheet_updates(posting.daily_preview_df, sheet.daily_rows)
    except Exception:
        daily_sheet_updates = []
    return {
        "ACCOUNTS": accounts_layout_preview(state, account_updates),
        "RECIEPT": receipt_layout_preview(state, receipt_updates),
        "DAILY": daily_layout_preview(state, daily_sheet_updates),
        "SCR VS BR": scr_layout_preview(state, posting.scr_updates),
    }


def sync_parsed_status_from_accounts_preview(parsed_df: pd.DataFrame, accounts_preview_df: pd.DataFrame) -> pd.DataFrame:
    if (
        parsed_df.empty
        or accounts_preview_df.empty
        or "Transaction Key" not in parsed_df
        or not {"Transaction Key", "Status", "Issue"}.issubset(accounts_preview_df.columns)
    ):
        return parsed_df
    synced = parsed_df.copy()
    preview_by_key = accounts_preview_df.dropna(subset=["Transaction Key"]).drop_duplicates("Transaction Key", keep="last")
    preview_by_key = preview_by_key.set_index(preview_by_key["Transaction Key"].astype(str))
    for row_index, key in synced["Transaction Key"].astype(str).items():
        if not key or key not in preview_by_key.index:
            continue
        preview_row = preview_by_key.loc[key]
        if accounts_duplicate_is_postable_elsewhere(preview_row):
            synced.at[row_index, "Status"] = "PASSED"
            synced.at[row_index, "Issue"] = ""
            continue
        synced.at[row_index, "Status"] = preview_row.get("Status", synced.at[row_index, "Status"] if "Status" in synced.columns else "PASSED")
        synced.at[row_index, "Issue"] = preview_row.get("Issue", synced.at[row_index, "Issue"] if "Issue" in synced.columns else "")
    return synced


class SimsoftWorkflowService:
    def __init__(
        self,
        duplicate_store: DuplicateAuditStore | None = None,
        sheets_gateway: GoogleSheetsGateway | None = None,
        audit_repository: AuditRepository | None = None,
        event_bus: EventBus | None = None,
        transaction_manager: PostingTransactionManager | None = None,
    ) -> None:
        self._worksheet_rows_cache: dict[str, dict[str, Any]] = {}
        self._folder_scan_cache: dict[str, dict[str, dict[str, Any]]] = {}
        self._duplicate_history_cache: set[str] | None = None
        self._ibp_account_lookup_cache: dict[str, dict[str, Any]] = {}
        self._ibp_branch_account_index_cache: dict[str, dict[str, Any]] = {}
        self._parsed_cache: dict[tuple[Any, ...], tuple[pd.DataFrame, str, list[str]]] = {}
        self._preview_cache: dict[tuple[Any, ...], dict[str, Any]] = {}
        self._last_parse_key: tuple[Any, ...] | None = None
        self._last_preview_key: tuple[Any, ...] | None = None
        self.performance_timings: dict[str, float] = {}
        self.duplicate_store = duplicate_store or LocalCsvDuplicateAuditStore()
        self.sheets_gateway = sheets_gateway or DefaultGoogleSheetsGateway()
        self.audit_repository = audit_repository or LocalCsvAuditRepository()
        self.event_bus = event_bus or InMemoryEventBus()
        self.transaction_manager = transaction_manager or PostingTransactionManager(self.duplicate_store)

    def publish_event(self, name: str, **payload: Any) -> None:
        self.event_bus.publish(ApplicationEvent(name=name, payload=payload))

    def clear_cache(self) -> None:
        self._worksheet_rows_cache.clear()
        self._preview_cache.clear()
        self._last_preview_key = None

    def clear_session_cache(self) -> None:
        self.clear_cache()
        self._folder_scan_cache.clear()
        self._duplicate_history_cache = None
        self._ibp_account_lookup_cache.clear()
        self._ibp_branch_account_index_cache.clear()
        self._parsed_cache.clear()
        self._last_parse_key = None

    @contextmanager
    def timed(self, state: AppState | None, label: str):
        start = perf_counter()
        try:
            yield
        finally:
            elapsed = perf_counter() - start
            self.performance_timings[label] = elapsed
            if state is not None:
                state.performance_timings[label] = elapsed

    def duplicate_history(self) -> set[str]:
        if self._duplicate_history_cache is None:
            self._duplicate_history_cache = self.duplicate_store.transaction_keys()
        return self._duplicate_history_cache

    def ensure_batch_id(self, state: AppState) -> str:
        if not state.posting.batch_id:
            state.posting.batch_id = new_batch_id()
        return state.posting.batch_id

    def sheet_snapshot(self, state: AppState) -> str:
        return self.rows_snapshot(
            state,
            state.sheet.accounts_rows,
            state.sheet.receipt_rows,
            state.sheet.daily_rows,
            state.sheet.scr_rows,
        )

    def rows_snapshot(
        self,
        state: AppState,
        accounts_rows: list[list[Any]],
        receipt_rows: list[list[Any]],
        daily_rows: list[list[Any]],
        scr_rows: list[list[Any]],
    ) -> str:
        payload = repr(
            (
                state.sheet.target_branch_id,
                state.sheet.target_spreadsheet_id,
                state.sheet.active_receipt_tab,
                state.sheet.active_daily_tab,
                accounts_rows,
                receipt_rows,
                daily_rows,
                scr_rows,
            )
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def fresh_sheet_snapshot(self, state: AppState) -> str:
        spreadsheet_id = extract_spreadsheet_id(state.sheet.sheet_url)
        client = self.sheets_gateway.client(state.auth_context)
        spreadsheet = client.open_by_key(spreadsheet_id)
        accounts_rows = spreadsheet.worksheet(TARGET_TAB).get_all_values()
        receipt_rows = spreadsheet.worksheet(state.sheet.active_receipt_tab).get_all_values()
        daily_rows = spreadsheet.worksheet(state.sheet.active_daily_tab).get_all_values()
        scr_rows = spreadsheet.worksheet(SCR_TAB).get_all_values()
        return self.rows_snapshot(state, accounts_rows, receipt_rows, daily_rows, scr_rows)

    def scan_drive_folder_cached(self, state: AppState, folder_url: str, refresh: bool = False) -> dict[str, dict[str, Any]]:
        folder_id = extract_drive_folder_id(folder_url)
        cache_key = f"{state.auth_mode}|{state.current_user_email}|{folder_id}"
        if not refresh and cache_key in self._folder_scan_cache:
            state.cache.branch_folder = "Cached"
            state.cache.branch_sheet_count = len(self._folder_scan_cache[cache_key])
            state.cache.branch_duplicate_warnings = duplicate_branch_warnings(self._folder_scan_cache[cache_key])
            return self._folder_scan_cache[cache_key]
        if not refresh:
            disk_cached = self.read_folder_scan_disk_cache(cache_key)
            if disk_cached is not None:
                self._folder_scan_cache[cache_key] = disk_cached
                state.performance_timings["drive_folder_scan_duration"] = 0.0
                state.cache.branch_folder = "Cached"
                state.cache.branch_sheet_count = len(disk_cached)
                state.cache.branch_duplicate_warnings = duplicate_branch_warnings(disk_cached)
                return disk_cached
        with self.timed(state, "drive_folder_scan_duration"):
            files = scan_branch_folder_metadata(state.auth_context, folder_id)
        with self.timed(state, "branch_index_build_duration"):
            index = build_branch_index(files)
        self._folder_scan_cache[cache_key] = index
        self.write_folder_scan_disk_cache(cache_key, folder_id, index)
        state.cache.branch_folder = "Scanned"
        state.cache.branch_sheet_count = len(index)
        state.cache.branch_scan_duration = state.performance_timings.get("drive_folder_scan_duration", 0.0)
        state.cache.branch_duplicate_warnings = duplicate_branch_warnings(index)
        state.cache.preview = "Stale"
        return index

    def read_folder_scan_disk_cache(self, cache_key: str) -> dict[str, dict[str, Any]] | None:
        if not FOLDER_SCAN_CACHE_PATH.exists():
            return None
        try:
            payload = json.loads(FOLDER_SCAN_CACHE_PATH.read_text(encoding="utf-8"))
            entry = payload.get(cache_key)
            if not entry:
                return None
            cached_at = float(entry.get("cached_at", 0))
            import time

            if time.time() - cached_at > FOLDER_SCAN_CACHE_TTL_SECONDS:
                return None
            index = entry.get("branch_index")
            return index if isinstance(index, dict) else None
        except Exception:
            return None

    def write_folder_scan_disk_cache(self, cache_key: str, folder_id: str, branch_index: dict[str, dict[str, Any]]) -> None:
        import time
        from datetime import datetime

        FOLDER_SCAN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {}
        if FOLDER_SCAN_CACHE_PATH.exists():
            try:
                payload = json.loads(FOLDER_SCAN_CACHE_PATH.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
        payload[cache_key] = {
            "folder_id": folder_id,
            "scanned_at": datetime.now().isoformat(timespec="seconds"),
            "cached_at": time.time(),
            "file_count": len(branch_index),
            "branch_index": branch_index,
        }
        FOLDER_SCAN_CACHE_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def reset_posting_state(self, state: AppState) -> None:
        state.sheet = GoogleSheetState()
        state.posting = PostingState()
        state.cache.branch_folder = "Not Scanned"
        state.cache.simsoft_parse = "Needs Upload"
        state.cache.preview = "Stale"
        state.cache.target_sheet = "Needs Revalidation"

    def select_target_branch(self, state: AppState, branch_id: str) -> None:
        branch_info = state.branch_index.get(branch_id, {})
        state.sheet.target_branch_id = branch_id
        state.sheet.target_branch_name = branch_info.get("branch_name", "")
        state.sheet.target_spreadsheet_id = branch_info.get("spreadsheet_id", "")
        state.sheet.sheet_url = (
            f"https://docs.google.com/spreadsheets/d/{state.sheet.target_spreadsheet_id}"
            if state.sheet.target_spreadsheet_id
            else ""
        )
        self.clear_cache()
        state.cache.preview = "Stale"
        state.cache.target_sheet = "Needs Revalidation"

    def parse_simsoft_file(self, state: AppState, file_path: Path) -> None:
        self.parse_simsoft_files(state, [file_path])

    def parse_simsoft_files(self, state: AppState, file_paths: list[Path]) -> None:
        if not file_paths:
            state.posting.errors.append("Choose at least one SIMSOFT Excel file.")
            state.cache.simsoft_parse = "Needs Upload"
            return
        state.simsoft_file_path = file_paths[0]
        state.posting.source_file = ", ".join(file_path.name for file_path in file_paths)
        self.ensure_batch_id(state)
        parse_key = (
            files_cache_key(file_paths),
            state.test_mode,
            state.auth_mode,
            state.current_user_email,
            branch_index_signature(state.branch_index),
        )
        if parse_key in self._parsed_cache:
            cached_df, cached_daily_tab, cached_errors = self._parsed_cache[parse_key]
            state.posting.parsed_df = cached_df.copy()
            state.sheet.active_daily_tab = cached_daily_tab
            state.posting.errors.extend(cached_errors)
            self._last_parse_key = parse_key
            state.cache.simsoft_parse = "Ready"
            state.cache.preview = "Stale"
            return

        with self.timed(state, "SIMSOFT Excel read"):
            raw_frames = [read_simsoft_excel(file_path) for file_path in file_paths]
            raw_df = pd.concat(raw_frames, ignore_index=True) if len(raw_frames) > 1 else raw_frames[0]
        duplicate_history = set() if state.test_mode else self.duplicate_history()
        with self.timed(state, "SIMSOFT validation"):
            parsed_df, parse_errors = parse_and_validate_simsoft(raw_df, duplicate_history)
        state.posting.parsed_df = parsed_df
        state.posting.errors.extend(parse_errors)
        if parsed_df.empty:
            self._parsed_cache[parse_key] = (parsed_df.copy(), state.sheet.active_daily_tab, list(parse_errors))
            self._last_parse_key = parse_key
            state.cache.simsoft_parse = "Needs Upload"
            return
        state.sheet.active_daily_tab, daily_errors = daily_tab_for_parsed_rows(parsed_df)
        state.posting.errors.extend(daily_errors)
        if state.auth_context and state.branch_index:
            with self.timed(state, "ibp_source_sheet_load_duration"):
                parsed_df = annotate_ibp_rows(
                    parsed_df,
                    state.branch_index,
                    state.auth_context,
                    self._ibp_account_lookup_cache,
                    self._ibp_branch_account_index_cache,
                )
            state.posting.parsed_df = parsed_df
        with self.timed(state, "Other Payment annotation"):
            parsed_df = annotate_other_payment_rows(parsed_df)
        state.posting.parsed_df = parsed_df
        cached_errors = [*parse_errors, *daily_errors]
        self._parsed_cache[parse_key] = (state.posting.parsed_df.copy(), state.sheet.active_daily_tab, cached_errors)
        self._last_parse_key = parse_key
        state.cache.simsoft_parse = "Ready"
        state.cache.preview = "Stale"

    def load_google_sheet(self, state: AppState) -> None:
        if not state.sheet.sheet_url or not state.auth_context:
            return

        sheet_state = state.sheet
        spreadsheet_id = extract_spreadsheet_id(sheet_state.sheet_url)
        spreadsheet = None

        def fetch_target_tab(tab_name: str) -> tuple[Any, list[list[Any]]]:
            nonlocal spreadsheet
            cache_key = f"{state.auth_mode}|{state.current_user_email}|{sheet_state.sheet_url}|{tab_name}"
            cached = self._worksheet_rows_cache.get(cache_key)
            if cached is not None:
                return cached["worksheet"], cached["rows"]
            if spreadsheet is None:
                client = self.sheets_gateway.client(state.auth_context)
                spreadsheet = client.open_by_key(spreadsheet_id)
            worksheet = spreadsheet.worksheet(tab_name)
            rows = worksheet.get_all_values()
            self._worksheet_rows_cache[cache_key] = {"worksheet": worksheet, "rows": rows}
            return worksheet, rows

        with self.timed(state, "target_sheet_load_duration"):
            sheet_state.accounts_worksheet, sheet_state.accounts_rows = fetch_target_tab(TARGET_TAB)
            sheet_state.accounts_headers = row_headers(sheet_state.accounts_rows, ACCOUNTS_HEADER_ROW)
            sheet_state.receipt_worksheet, sheet_state.receipt_rows, sheet_state.active_receipt_tab = fetch_first_available_tab_with_fetcher(
                fetch_target_tab,
                RECEIPT_TAB_ALIASES,
            )
            sheet_state.receipt_headers = row_headers(sheet_state.receipt_rows, RECEIPT_HEADER_ROW)
            if not state.posting.parsed_df.empty:
                sheet_state.daily_worksheet, sheet_state.daily_rows, sheet_state.active_daily_tab = fetch_first_available_tab_with_fetcher(
                    fetch_target_tab,
                    daily_tab_aliases(sheet_state.active_daily_tab),
                )
            sheet_state.scr_worksheet, sheet_state.scr_rows = fetch_target_tab(SCR_TAB)
        sheet_state.google_ready = bool(
            sheet_state.accounts_worksheet is not None
            and sheet_state.receipt_worksheet is not None
            and sheet_state.scr_worksheet is not None
            and (state.posting.parsed_df.empty or sheet_state.daily_worksheet is not None)
        )
        if sheet_state.google_ready:
            state.posting.validation_snapshot = self.sheet_snapshot(state)
            state.cache.target_sheet = "Freshly Validated"

    def build_previews(self, state: AppState, include_review_artifacts: bool = True) -> None:
        posting = state.posting
        sheet = state.sheet
        if posting.parsed_df.empty or not sheet.google_ready:
            return
        preview_key = (
            self._last_parse_key,
            sheet.target_spreadsheet_id,
            sheet.active_receipt_tab,
            sheet.active_daily_tab,
            id(sheet.accounts_rows),
            id(sheet.receipt_rows),
            id(sheet.daily_rows),
            id(sheet.scr_rows),
        )
        if preview_key in self._preview_cache:
            cached = self._preview_cache[preview_key]
            posting.accounts_preview_df = cached["accounts_preview_df"].copy()
            posting.parsed_df = sync_parsed_status_from_accounts_preview(posting.parsed_df, posting.accounts_preview_df)
            posting.receipt_preview_df = cached["receipt_preview_df"].copy()
            posting.daily_preview_df = cached["daily_preview_df"].copy()
            posting.scr_preview_df = cached["scr_preview_df"].copy()
            posting.scr_updates = [dict(update) for update in cached["scr_updates"]]
            posting.sheet_layouts = dict(cached.get("sheet_layouts") or {})
            posting.ai_resolver = dict(cached.get("ai_resolver") or {})
            posting.errors.extend(cached["errors"])
            self._last_preview_key = preview_key
            posting.validated_at = iso_now()
            posting.validation_snapshot = self.sheet_snapshot(state)
            posting.validation_snapshot_id = hashlib.sha256(posting.validation_snapshot.encode("utf-8")).hexdigest()[:16]
            state.cache.preview = "Fresh"
            state.cache.target_sheet = "Freshly Validated"
            return

        with self.timed(state, "Preview generation"):
            posting.accounts_preview_df, account_errors = prepare_accounts_preview(
                posting.parsed_df,
                sheet.accounts_rows,
                sheet.accounts_headers,
                ACCOUNTS_HEADER_ROW,
            )
            posting.parsed_df = sync_parsed_status_from_accounts_preview(posting.parsed_df, posting.accounts_preview_df)
            posting.receipt_preview_df, receipt_errors = prepare_receipt_preview(
                posting.parsed_df,
                sheet.target_branch_name,
                sheet.receipt_rows,
                sheet.receipt_headers,
                RECEIPT_HEADER_ROW,
            )
            posting.daily_preview_df = prepare_daily_preview(posting.parsed_df, sheet.active_daily_tab)
            posting.scr_preview_df, posting.scr_updates, scr_errors = prepare_scr_vs_br_updates(
                posting.parsed_df,
                sheet.scr_rows,
                posting.receipt_preview_df,
            )
        posting.errors.extend(account_errors)
        posting.errors.extend(receipt_errors)
        posting.errors.extend(scr_errors)
        if include_review_artifacts:
            with self.timed(state, "Sheet layout preview build"):
                posting.sheet_layouts = build_sheet_layout_previews(state)
            with self.timed(state, "AI resolver review"):
                ai_context = build_ai_resolver_context(
                    parsed_df=posting.parsed_df,
                    accounts_preview_df=posting.accounts_preview_df,
                    receipt_preview_df=posting.receipt_preview_df,
                    daily_preview_df=posting.daily_preview_df,
                    scr_preview_df=posting.scr_preview_df,
                    accounts_rows=sheet.accounts_rows,
                    accounts_headers=sheet.accounts_headers,
                    receipt_rows=sheet.receipt_rows,
                    receipt_headers=sheet.receipt_headers,
                    daily_rows=sheet.daily_rows,
                    scr_rows=sheet.scr_rows,
                    scr_updates=posting.scr_updates,
                    active_receipt_tab=sheet.active_receipt_tab,
                    active_daily_tab=sheet.active_daily_tab,
                    target_branch_id=sheet.target_branch_id,
                    target_branch_name=sheet.target_branch_name,
                    errors=[*account_errors, *receipt_errors, *scr_errors],
                )
                posting.ai_resolver = resolve_posting_with_gemini(ai_context)
        else:
            posting.sheet_layouts = {}
            posting.ai_resolver = {}
        preview_errors = [*account_errors, *receipt_errors, *scr_errors]
        if include_review_artifacts:
            self._preview_cache[preview_key] = {
                "accounts_preview_df": posting.accounts_preview_df.copy(),
                "receipt_preview_df": posting.receipt_preview_df.copy(),
                "daily_preview_df": posting.daily_preview_df.copy(),
                "scr_preview_df": posting.scr_preview_df.copy(),
                "scr_updates": [dict(update) for update in posting.scr_updates],
                "sheet_layouts": dict(posting.sheet_layouts),
                "ai_resolver": dict(posting.ai_resolver),
                "errors": preview_errors,
            }
        self._last_preview_key = preview_key
        self.ensure_batch_id(state)
        posting.validated_at = iso_now()
        posting.validation_snapshot = self.sheet_snapshot(state)
        posting.validation_snapshot_id = hashlib.sha256(posting.validation_snapshot.encode("utf-8")).hexdigest()[:16]
        posting.row_count = int(len(posting.parsed_df))
        posting.duplicate_count = int((posting.parsed_df["Status"] == "DUPLICATE").sum()) if "Status" in posting.parsed_df else 0
        state.cache.preview = "Fresh"
        state.cache.target_sheet = "Freshly Validated"
        self.publish_event(
            "PostingPreviewBuilt",
            batch_id=posting.batch_id,
            target_branch_id=sheet.target_branch_id,
            target_spreadsheet_id=sheet.target_spreadsheet_id,
            row_count=posting.row_count,
            duplicate_count=posting.duplicate_count,
            include_review_artifacts=include_review_artifacts,
        )
        if include_review_artifacts:
            with self.timed(state, "Audit log generation"):
                self.write_preview_audit(state)

    def branch_is_locked(self, state: AppState) -> bool:
        if not state.sheet.target_branch_id or not state.sheet.target_spreadsheet_id:
            return False
        if not hasattr(self.duplicate_store, "is_branch_locked"):
            return False
        return self.duplicate_store.is_branch_locked(branch_lock_key(state.sheet.target_branch_id, state.sheet.target_spreadsheet_id))

    def recompute_posting_gate(self, state: AppState) -> list[str]:
        posting = state.posting
        parsed_errors = bool(not posting.parsed_df.empty and "Status" in posting.parsed_df and (posting.parsed_df["Status"] == "ERROR").any())
        postable_keys = passed_transaction_keys(posting.accounts_preview_df)
        preview_errors = any(
            [
                preview_has_blocking_errors(posting.accounts_preview_df),
                preview_has_blocking_errors(posting.receipt_preview_df, postable_keys),
                preview_has_blocking_errors(posting.daily_preview_df, postable_keys),
                preview_has_blocking_errors(posting.scr_preview_df, postable_keys),
            ]
        )
        preview_error_tabs = [
            tab_name
            for tab_name, df, keys in [
                ("ACCOUNTS", posting.accounts_preview_df, None),
                (state.sheet.active_receipt_tab or "RECIEPT", posting.receipt_preview_df, postable_keys),
                (state.sheet.active_daily_tab or "Daily", posting.daily_preview_df, postable_keys),
                ("SCR VS BR", posting.scr_preview_df, postable_keys),
            ]
            if preview_has_blocking_errors(df, keys)
        ]
        preview_issue_details: list[str] = []
        for tab_name, df, keys in [
            ("ACCOUNTS", posting.accounts_preview_df, None),
            (state.sheet.active_receipt_tab or "RECIEPT", posting.receipt_preview_df, postable_keys),
            (state.sheet.active_daily_tab or "Daily", posting.daily_preview_df, postable_keys),
            ("SCR VS BR", posting.scr_preview_df, postable_keys),
        ]:
            preview_issue_details.extend(preview_blocking_issue_summary(tab_name, df, keys))
        duplicates = False
        visible_errors = unique_messages(posting.errors)
        ibp_issue = bool(not posting.parsed_df.empty and "ibp_lookup_status" in posting.parsed_df and (posting.parsed_df["ibp_lookup_status"].astype(str).isin(["ERROR", "NEEDS REVIEW"])).any())
        other_issue = any("Other Payment" in error or "OTHER PAYMENT" in error for error in visible_errors)
        scr_issue = any("SCR" in error.upper() for error in visible_errors)
        folder_scan_complete = bool(state.branch_index)
        preview_fresh = state.cache.preview == "Fresh" and bool(posting.validation_snapshot)
        branch_locked = self.branch_is_locked(state)
        wrong_branch_rows = rows_for_different_branch(posting.parsed_df, state.sheet.target_branch_id)
        wrong_branch_issue = not wrong_branch_rows.empty
        blocking_errors = bool(visible_errors or parsed_errors or preview_errors or duplicates or ibp_issue or other_issue or scr_issue or wrong_branch_issue)
        posting.can_post = can_swipe_to_post(
            state.sheet.google_ready,
            not posting.parsed_df.empty,
            blocking_errors,
            ENABLE_LIVE_POSTING,
            auth_signed_in=state.auth_ready,
            preview_fresh=preview_fresh,
            target_branch_selected=bool(state.sheet.target_branch_id),
            folder_scan_complete=folder_scan_complete,
            branch_unlocked=not branch_locked,
        )
        lock_reasons: list[str] = []
        if not state.auth_ready:
            lock_reasons.append("Google authentication required.")
        if not folder_scan_complete:
            lock_reasons.append("Folder scan required.")
        if not state.sheet.target_branch_id:
            lock_reasons.append("Select target branch first.")
        if state.sheet.target_branch_id and state.branch_index.get(state.sheet.target_branch_id, {}).get("status") == "MULTIPLE_MATCHES":
            blocking_errors = True
            posting.can_post = False
            lock_reasons.append("Duplicate branch ID must be fixed before posting.")
        if not preview_fresh:
            lock_reasons.append("Preview is stale. Please revalidate.")
        if not state.sheet.google_ready:
            lock_reasons.append("Google Sheet connection is not ready.")
        if posting.parsed_df.empty:
            lock_reasons.append("SIMSOFT file is not parsed.")
        lock_reasons.extend(visible_errors)
        if parsed_errors:
            lock_reasons.append("Validation errors must be fixed.")
        if preview_errors:
            missing_branch_rows = accounts_missing_from_target_branch(posting.accounts_preview_df)
            if not missing_branch_rows.empty:
                lock_reasons.append("Wrong branch")
                lock_reasons.append(
                    f"Selected branch: {state.sheet.target_branch_id} - {state.sheet.target_branch_name}. "
                    "Choose the correct branch folder/sheet, then rebuild previews."
                )
                missing_names = [
                    str(row.get("Account Name", "") or row.get("Account", "")).strip()
                    for row in missing_branch_rows.head(3).to_dict("records")
                    if str(row.get("Account Name", "") or row.get("Account", "")).strip()
                ]
                if missing_names:
                    lock_reasons.append(f"Missing account(s): {', '.join(missing_names)}.")
                remaining_missing = len(missing_branch_rows) - len(missing_names)
                if remaining_missing > 0:
                    lock_reasons.append(f"+{remaining_missing} more missing account(s).")
                receipt_errors = [detail for detail in preview_issue_details if not detail.startswith("ACCOUNTS:")]
                if receipt_errors:
                    lock_reasons.append("Other validation issue(s):")
                    lock_reasons.extend(receipt_errors)
            else:
                lock_reasons.append(f"Validation errors must be fixed in: {', '.join(preview_error_tabs)}.")
                lock_reasons.extend(preview_issue_details)
        if wrong_branch_issue:
            lock_reasons.append("Wrong branch")
            source_branches = sorted(
                {
                    normalize_text(value).upper().split("-", 1)[0]
                    for value in wrong_branch_rows["Account Number"].tolist()
                    if "-" in normalize_text(value)
                }
            )
            source_text = ", ".join(source_branches[:3]) or "another branch"
            lock_reasons.append(
                f"SIMSOFT file is for {source_text}, but selected branch is "
                f"{state.sheet.target_branch_id} - {state.sheet.target_branch_name}."
            )
            sample_accounts = [
                str(row.get("Account Number", "")).strip()
                for row in wrong_branch_rows.head(3).to_dict("records")
                if str(row.get("Account Number", "")).strip()
            ]
            if sample_accounts:
                lock_reasons.append(f"Sample account(s): {', '.join(sample_accounts)}.")
        if ibp_issue:
            lock_reasons.append("Unresolved IBP lookup issue.")
        if other_issue:
            lock_reasons.append("Unresolved Other Payment issue.")
        if scr_issue:
            lock_reasons.append("Unresolved SCR VS BR issue.")
        if branch_locked:
            lock_reasons.append("Branch is locked by another operator.")
        if not ENABLE_LIVE_POSTING:
            lock_reasons.append("Live posting is disabled in core/settings.py.")
        posting.post_lock_reason = unique_messages(lock_reasons)[0] if lock_reasons else ""
        return unique_messages(lock_reasons)

    def summary(self, state: AppState) -> dict[str, Any]:
        return calculate_summary(state.posting.parsed_df)

    def combined_preview(self, state: AppState) -> pd.DataFrame:
        parts = [
            df
            for df in [
                state.posting.accounts_preview_df,
                state.posting.receipt_preview_df,
                state.posting.daily_preview_df,
                state.posting.scr_preview_df,
            ]
            if not df.empty
        ]
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()

    def fully_paid_cash_export(self, state: AppState) -> pd.DataFrame:
        if state.posting.accounts_preview_df.empty or not state.sheet.accounts_rows or not state.sheet.accounts_headers:
            return pd.DataFrame(columns=["Account", "Code"])
        return build_fully_paid_cash_export(
            state.posting.accounts_preview_df,
            state.sheet.accounts_rows,
            state.sheet.accounts_headers,
        )

    def write_preview_audit(self, state: AppState) -> Path | None:
        all_preview_df = self.combined_preview(state)
        if all_preview_df.empty:
            return None
        all_preview_df = all_preview_df.copy()
        all_preview_df["target_branch_id"] = state.sheet.target_branch_id
        all_preview_df["target_branch_name"] = state.sheet.target_branch_name
        all_preview_df["target_spreadsheet_id"] = state.sheet.target_spreadsheet_id
        path = self.audit_repository.write(
            all_preview_df,
            new_batch_id(),
            state.sheet.sheet_url,
            state.posting.source_file,
            [TARGET_TAB, state.sheet.active_receipt_tab, state.sheet.active_daily_tab, SCR_TAB],
            self.auth_metadata(state),
        )
        self.publish_event(
            "PostingPreviewAuditWritten",
            target_branch_id=state.sheet.target_branch_id,
            target_spreadsheet_id=state.sheet.target_spreadsheet_id,
            path=str(path),
        )
        return path

    def auth_metadata(self, state: AppState) -> dict[str, Any]:
        actor = state.service_account_email if state.auth_mode == AUTH_MODE_SERVICE_ACCOUNT else state.current_user_email or state.service_account_email
        posted_tabs = state.posting.posted_target_tabs or [TARGET_TAB, state.sheet.active_receipt_tab, state.sheet.active_daily_tab, SCR_TAB]
        return {
            "auth_mode": state.auth_mode,
            "google_actor_email": actor,
            "operator_email": state.current_user_email,
            "posted_by_email": actor,
            "posted_by_google_user": state.current_user_email if state.current_user_email != state.service_account_email else "",
            "token_user_email": state.token_user_email,
            "operator_name": state.operator_name or state.current_user_name,
            "started_at": state.posting.validated_at,
            "posted_at": state.posting.posted_at,
            "lock_acquired_at": state.posting.lock_acquired_at,
            "lock_released_at": state.posting.lock_released_at,
            "branch_lock_id": branch_lock_key(state.sheet.target_branch_id, state.sheet.target_spreadsheet_id) if state.sheet.target_branch_id else "",
            "validation_snapshot_id": state.posting.validation_snapshot_id,
            "preview_generated_at": state.posting.validated_at,
            "confirmation_method": "swipe_to_post",
            "row_count": state.posting.row_count,
            "posted_tabs": ", ".join(posted_tabs),
            "errors": "; ".join(unique_messages(state.posting.errors)),
            "duplicate_count": state.posting.duplicate_count,
        }

    def duplicate_transaction_conflicts(self, state: AppState) -> set[str]:
        if state.test_mode or state.posting.parsed_df.empty or "Transaction Key" not in state.posting.parsed_df:
            return set()
        keys = [
            key
            for key in state.posting.parsed_df.loc[state.posting.parsed_df["Status"] == "PASSED", "Transaction Key"].tolist()
            if key
        ]
        return self.transaction_manager.existing_transaction_keys(keys)

    def build_ibp_source_branch_posts(self, state: AppState) -> list[tuple[Any, list[dict[str, Any]]]]:
        posting = state.posting
        if posting.parsed_df.empty or "is_ibp" not in posting.parsed_df:
            return []
        ibp_rows = posting.parsed_df[
            (posting.parsed_df["is_ibp"].astype(bool))
            & (posting.parsed_df["Status"].astype(str) == "PASSED")
        ]
        if ibp_rows.empty:
            return []
        missing_keys = [
            str(row.get("OR Number", "")).strip() or str(row.get("Reference", "")).strip()
            for row in ibp_rows.to_dict("records")
            if not posting.ibp_particulars.get(str(row.get("Transaction Key", "")).strip(), "").strip()
        ]
        if missing_keys:
            raise ValueError(f"IBP particular is required before posting: {', '.join(missing_keys)}")

        client = self.sheets_gateway.client(state.auth_context)
        posts: list[tuple[Any, list[dict[str, Any]]]] = []
        for source_branch_id, group in ibp_rows.groupby("ibp_source_branch_id"):
            branch_id = normalize_text(source_branch_id).upper()
            branch = state.branch_index.get(branch_id)
            if not branch:
                raise ValueError(f"Branch sheet not found for IBP source branch {branch_id}.")
            spreadsheet_id = str(branch.get("spreadsheet_id") or "").strip()
            if not spreadsheet_id:
                raise ValueError(f"IBP source branch {branch_id} does not have a Google Spreadsheet ID.")
            worksheet = client.open_by_key(spreadsheet_id).worksheet(TARGET_TAB)
            rows = worksheet.get_all_values()
            headers = row_headers(rows, ACCOUNTS_HEADER_ROW)
            updates = prepare_ibp_source_branch_updates(
                group,
                rows,
                headers,
                ACCOUNTS_HEADER_ROW,
                posting.ibp_particulars,
                state.sheet.target_branch_name,
                posting.ibp_payment_breakdowns,
            )
            if updates:
                posts.append((worksheet, updates))
        return posts

    def ensure_validation_current(self, state: AppState) -> None:
        if not state.posting.validation_snapshot:
            raise PermissionError("Validated preview state is not ready. Please validate before posting.")
        if self.sheet_snapshot(state) != state.posting.validation_snapshot:
            state.cache.preview = "Stale"
            state.cache.target_sheet = "Needs Revalidation"
            raise PermissionError("The sheet changed after validation. Please revalidate before posting.")
        if not state.test_mode and state.auth_context and state.sheet.sheet_url:
            with self.timed(state, "Pre-post conflict check"):
                if self.fresh_sheet_snapshot(state) != state.posting.validation_snapshot:
                    state.cache.preview = "Stale"
                    state.cache.target_sheet = "Needs Revalidation"
                    raise PermissionError("The sheet changed after validation. Please revalidate before posting.")

    def acquire_posting_lock(self, state: AppState) -> BranchLock:
        if not state.sheet.target_branch_id or not state.sheet.target_spreadsheet_id:
            raise PermissionError("Target branch is not selected.")
        batch_id = self.ensure_batch_id(state)
        return self.transaction_manager.acquire_branch_lock(
            target_branch_id=state.sheet.target_branch_id,
            target_spreadsheet_id=state.sheet.target_spreadsheet_id,
            batch_id=batch_id,
            operator_email=state.current_user_email or state.service_account_email,
            operator_name=state.current_user_name or state.operator_name,
        )

    def post(self, state: AppState) -> int:
        sheet = state.sheet
        posting = state.posting
        if not posting.can_post:
            raise PermissionError("Posting is locked.")
        batch_id = self.ensure_batch_id(state)
        if not state.test_mode and self.transaction_manager.batch_exists(batch_id):
            return 0
        self.ensure_validation_current(state)
        duplicate_conflicts = self.duplicate_transaction_conflicts(state)
        if duplicate_conflicts:
            raise PermissionError("Some transactions were already posted by another operator. Please refresh and revalidate.")
        lock: BranchLock | None = None
        posting_error: Exception | None = None
        try:
            lock = self.acquire_posting_lock(state)
            posting.lock_acquired_at = lock.acquired_at
            with self.timed(state, "Posting operation build"):
                postable_keys = passed_transaction_keys(posting.accounts_preview_df)
                receipt_preview = filter_preview_to_transaction_keys(posting.receipt_preview_df, postable_keys)
                daily_preview = filter_preview_to_transaction_keys(posting.daily_preview_df, postable_keys)
                account_updates = prepare_sheet_updates(posting.accounts_preview_df, sheet.accounts_rows, sheet.accounts_headers)
                daily_updates, daily_errors = prepare_daily_collection_updates(posting.accounts_preview_df, sheet.accounts_rows)
                daily_sheet_updates, daily_sheet_errors = prepare_daily_sheet_updates(daily_preview, sheet.daily_rows)
                ibp_source_posts = self.build_ibp_source_branch_posts(state)
            daily_errors.extend(daily_sheet_errors)
            if daily_errors:
                raise ValueError("\n".join(daily_errors))
            with self.timed(state, "Google Sheet write/post"):
                receipt_updates = prepare_receipt_updates(receipt_preview, sheet.receipt_headers)
                posting.posted_target_tabs = []
                self.sheets_gateway.post_updates(sheet.accounts_worksheet, account_updates + daily_updates)
                posting.posted_target_tabs.append(TARGET_TAB)
                for ibp_worksheet, ibp_updates in ibp_source_posts:
                    self.sheets_gateway.post_updates(ibp_worksheet, ibp_updates)
                    source_branch = getattr(ibp_worksheet, "spreadsheet", None)
                    source_title = getattr(source_branch, "title", "") or "IBP SOURCE"
                    posting.posted_target_tabs.append(f"{source_title}:{TARGET_TAB}")
                self.sheets_gateway.post_updates(sheet.receipt_worksheet, receipt_updates)
                posting.posted_target_tabs.append(sheet.active_receipt_tab)
                self.sheets_gateway.post_updates(sheet.daily_worksheet, daily_sheet_updates)
                posting.posted_target_tabs.append(sheet.active_daily_tab)
                self.sheets_gateway.post_updates(sheet.scr_worksheet, posting.scr_updates)
                posting.posted_target_tabs.append(SCR_TAB)
            posting.posted_at = iso_now()
            posting.last_post_status = "POSTED"
            self.publish_event(
                "PostingPreviewPosted",
                batch_id=batch_id,
                target_branch_id=sheet.target_branch_id,
                target_spreadsheet_id=sheet.target_spreadsheet_id,
                target_tabs=list(posting.posted_target_tabs),
            )
        except BranchLockError as exc:
            posting.last_post_status = "LOCKED"
            posting_error = exc
        except Exception as exc:
            posting.last_post_status = "ERROR"
            posting_error = exc
            if str(exc) not in posting.errors:
                posting.errors.append(str(exc))
        finally:
            if lock is not None:
                posting.lock_released_at = self.transaction_manager.release_branch_lock(lock)
        if posting_error is not None:
            self.write_final_audit(state)
            raise posting_error
        self.clear_cache()
        self.write_final_audit(state)
        if state.test_mode:
            return 0
        with self.timed(state, "Duplicate history append"):
            count = self.transaction_manager.record_posted_batch(
                batch_id=batch_id,
                operator_email=state.current_user_email or state.service_account_email,
                target_branch_id=sheet.target_branch_id,
                target_tabs=[TARGET_TAB, sheet.active_receipt_tab, sheet.active_daily_tab, SCR_TAB],
                records=posting.parsed_df.to_dict("records"),
                posted_at=posting.posted_at,
            )
        self.publish_event(
            "DuplicateHistoryRecorded",
            batch_id=batch_id,
            target_branch_id=sheet.target_branch_id,
            recorded_count=count,
        )
        if self._duplicate_history_cache is not None:
            self._duplicate_history_cache.update(
                row.get("Transaction Key", "")
                for row in posting.parsed_df.to_dict("records")
                if row.get("Status") == "PASSED" and row.get("Transaction Key")
            )
        return count

    def write_final_audit(self, state: AppState) -> Path | None:
        all_preview_df = self.combined_preview(state)
        if all_preview_df.empty:
            return None
        all_preview_df = all_preview_df.copy()
        all_preview_df["target_branch_id"] = state.sheet.target_branch_id
        all_preview_df["target_branch_name"] = state.sheet.target_branch_name
        all_preview_df["target_spreadsheet_id"] = state.sheet.target_spreadsheet_id
        path = self.audit_repository.write(
            all_preview_df,
            self.ensure_batch_id(state),
            state.sheet.sheet_url,
            state.posting.source_file,
            [TARGET_TAB, state.sheet.active_receipt_tab, state.sheet.active_daily_tab, SCR_TAB],
            self.auth_metadata(state),
        )
        self.publish_event(
            "PostingFinalAuditWritten",
            batch_id=state.posting.batch_id,
            target_branch_id=state.sheet.target_branch_id,
            target_spreadsheet_id=state.sheet.target_spreadsheet_id,
            path=str(path),
            status=state.posting.last_post_status,
        )
        return path


def spreadsheet_url_from_id_or_url(value: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{extract_spreadsheet_id(value)}"
