from __future__ import annotations

import json
import math
import shutil
import sys
from contextlib import redirect_stdout
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.parser import read_simsoft_excel  # noqa: E402
from core.audit import HISTORY_COLUMNS, ensure_history_file  # noqa: E402
from core.concurrency import POSTED_BATCH_COLUMNS  # noqa: E402
from core.settings import DEFAULT_DUPLICATE_HISTORY_PATH, DEFAULT_POSTED_BATCHES_PATH  # noqa: E402
from core.google_sheets import (  # noqa: E402
    AUTH_MODE_SERVICE_ACCOUNT,
    AUTH_MODE_USER_OAUTH,
    DEFAULT_OAUTH_CLIENT_PATH,
    DEFAULT_OAUTH_TOKEN_DIR,
    clear_user_oauth_credentials,
    get_oauth_user_info,
    get_gspread_client,
    load_user_oauth_credentials,
    run_user_oauth_login,
    row_headers,
)
from core.accounts import build_account_index  # noqa: E402
from core.validation import calculate_summary, parse_and_validate_simsoft  # noqa: E402
from python_backend.services.workflow_service import load_service_account_context, scan_drive_folder  # noqa: E402
from python_backend.services.workflow_service import ACCOUNTS_HEADER_ROW, TARGET_TAB  # noqa: E402
from python_backend.models.app_state import AppState  # noqa: E402
from python_backend.services.workflow_service import SimsoftWorkflowService  # noqa: E402

DUPLICATE_HISTORY_PATH = Path(DEFAULT_DUPLICATE_HISTORY_PATH)
POSTED_BATCHES_PATH = Path(DEFAULT_POSTED_BATCHES_PATH)


def auth_mode_for_payload(payload: dict[str, Any] | None = None) -> str:
    mode = str((payload or {}).get("authMode") or "").strip().lower()
    if mode == "user_oauth":
        return AUTH_MODE_USER_OAUTH
    return AUTH_MODE_SERVICE_ACCOUNT


def to_jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return ""
    if hasattr(value, "item"):
        try:
            return to_jsonable(value.item())
        except Exception:
            pass
    try:
        if pd.isna(value) and not isinstance(value, (list, dict, tuple)):
            return ""
    except Exception:
        pass
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    return value


def dataframe_records(frame: Any) -> list[dict[str, Any]]:
    if frame is None or getattr(frame, "empty", True):
        return []
    return to_jsonable(frame.to_dict("records"))


def visible_accounts_number(rows: list[list[Any]], headers: list[str]) -> int:
    try:
        number_col = next(
            index
            for index, header in enumerate(headers)
            if str(header).strip() in {"#", "NO.", "No.", "NO"}
        )
    except StopIteration:
        try:
            return len(build_account_index(rows, headers, ACCOUNTS_HEADER_ROW))
        except Exception:
            return 0

    highest = 0
    for row in rows[ACCOUNTS_HEADER_ROW:]:
        if number_col >= len(row):
            continue
        text = str(row[number_col]).strip().replace(",", "")
        if not text.isdigit():
            continue
        highest = max(highest, int(text))
    return highest


def parse_simsoft(payload: dict[str, Any]) -> dict[str, Any]:
    file_paths = selected_file_paths(payload)
    duplicate_history = set(payload.get("duplicateHistory") or [])
    raw_frames = [read_simsoft_excel(file_path) for file_path in file_paths]
    raw_df = pd.concat(raw_frames, ignore_index=True) if len(raw_frames) > 1 else raw_frames[0]
    parsed_df, errors = parse_and_validate_simsoft(raw_df, duplicate_history)
    return {
        "rows": to_jsonable(parsed_df.to_dict("records")),
        "errors": errors,
        "summary": to_jsonable(calculate_summary(parsed_df)),
        "parser": "python-core",
    }


def selected_file_paths(payload: dict[str, Any]) -> list[Path]:
    raw_paths = payload.get("filePaths")
    if isinstance(raw_paths, list) and raw_paths:
        return [Path(str(path)) for path in raw_paths]
    return [Path(payload["filePath"])]


def scan_google_folder(payload: dict[str, Any]) -> dict[str, Any]:
    folder_url = str(payload.get("folderUrl", "")).strip()
    if not folder_url:
        raise ValueError("Google Drive branch folder link is required.")
    if auth_mode_for_payload(payload) == AUTH_MODE_USER_OAUTH:
        credentials, email = load_user_oauth_credentials(DEFAULT_OAUTH_TOKEN_DIR)
        if credentials is None:
            raise PermissionError("Google operator login is required before scanning the Drive folder.")
        auth_context = {"credentials": credentials, "current_user_email": email, "current_user_name": email.split("@", 1)[0]}
        service_account_email = email
    else:
        auth_context, service_account_email = load_service_account_context()
    branch_index = scan_drive_folder(auth_context, folder_url)
    return {
        "branchIndex": to_jsonable(branch_index),
        "serviceAccountEmail": service_account_email,
        "branchCount": len(branch_index),
        "duplicateWarnings": [
            f"{branch_id} has multiple matching files: {', '.join(info.get('matching_file_names') or [])}"
            for branch_id, info in sorted(branch_index.items())
            if info.get("status") == "MULTIPLE_MATCHES"
        ],
    }


def operator_payload(credentials: Any | None, email: str, error: str = "") -> dict[str, Any]:
    name = ""
    if credentials is not None:
        try:
            info = get_oauth_user_info(credentials)
            email = info.get("email") or email
            name = info.get("name") or ""
        except Exception:
            name = email.split("@", 1)[0] if email else ""
    return {
        "email": email,
        "name": name or (email.split("@", 1)[0] if email else ""),
        "signedIn": bool(credentials is not None and email),
        "tokenUserEmail": email,
        "authMode": "user_oauth",
        "error": error,
    }


def operator_identity(_: dict[str, Any]) -> dict[str, Any]:
    credentials, email = load_user_oauth_credentials(DEFAULT_OAUTH_TOKEN_DIR)
    return operator_payload(credentials, email)


def operator_login_google(_: dict[str, Any]) -> dict[str, Any]:
    credentials, email = run_user_oauth_login(DEFAULT_OAUTH_CLIENT_PATH, DEFAULT_OAUTH_TOKEN_DIR)
    return operator_payload(credentials, email)


def operator_logout_google(_: dict[str, Any]) -> dict[str, Any]:
    credentials, email = load_user_oauth_credentials(DEFAULT_OAUTH_TOKEN_DIR)
    clear_user_oauth_credentials(email or None, DEFAULT_OAUTH_TOKEN_DIR)
    return operator_payload(None, "")


def state_auth_context(payload: dict[str, Any], service_account_context: dict[str, Any], service_account_email: str) -> tuple[Any, str, str, str, str, str]:
    operator = payload.get("operatorIdentity") or {}
    operator_email = str(operator.get("email") or "").strip()
    operator_name = str(operator.get("name") or "").strip()
    token_user_email = str(operator.get("tokenUserEmail") or operator_email).strip()
    auth_mode = auth_mode_for_payload(payload)
    if auth_mode == AUTH_MODE_USER_OAUTH:
        credentials, email = load_user_oauth_credentials(DEFAULT_OAUTH_TOKEN_DIR)
        if credentials is None:
            raise PermissionError("Google operator login is required before using User OAuth mode.")
        info = get_oauth_user_info(credentials)
        operator_email = info.get("email") or email
        operator_name = info.get("name") or operator_email.split("@", 1)[0]
        token_user_email = email
        return (
            {
                "credentials": credentials,
                "current_user_email": operator_email,
                "current_user_name": operator_name,
            },
            auth_mode,
            operator_email,
            operator_name,
            token_user_email,
            service_account_email,
        )
    return (
        service_account_context,
        auth_mode,
        operator_email or service_account_email,
        operator_name or (operator_email.split("@", 1)[0] if operator_email else "Service Account"),
        token_user_email if operator_email else "",
        service_account_email,
    )


def prepare_preview_state(payload: dict[str, Any], include_review_artifacts: bool = True) -> tuple[SimsoftWorkflowService, AppState]:
    file_paths = selected_file_paths(payload)
    branch_id = str(payload.get("branchId", "")).strip()
    branch_index = payload.get("branchIndex") or {}
    if not branch_id:
        raise ValueError("Select target branch first.")
    if not branch_index or branch_id not in branch_index:
        raise ValueError("Folder scan required before building Google previews.")

    if auth_mode_for_payload(payload) == AUTH_MODE_USER_OAUTH:
        service_account_context, service_account_email = {}, ""
    else:
        service_account_context, service_account_email = load_service_account_context()
    auth_context, auth_mode, current_user_email, current_user_name, token_user_email, service_account_email = state_auth_context(
        payload,
        service_account_context,
        service_account_email,
    )
    service = SimsoftWorkflowService()
    state = AppState(
        auth_mode=auth_mode,
        auth_ready=True,
        auth_context=auth_context,
        current_user_email=current_user_email,
        service_account_email=service_account_email,
        current_user_name=current_user_name,
        token_user_email=token_user_email,
        operator_name=current_user_name,
        branch_index=branch_index,
        test_mode=bool(payload.get("testMode", False)),
    )
    state.branch_folder_url = str(payload.get("folderUrl", ""))
    state.posting.ibp_particulars = {str(key): str(value).strip() for key, value in (payload.get("ibpParticulars") or {}).items()}
    state.posting.ibp_payment_breakdowns = {
        str(key): {
            "rebate": str((value or {}).get("rebate", "")).strip() if isinstance(value, dict) else "",
            "amount": str((value or {}).get("amount", "")).strip() if isinstance(value, dict) else "",
            "penalty": str((value or {}).get("penalty", "")).strip() if isinstance(value, dict) else "",
        }
        for key, value in (payload.get("ibpPaymentBreakdowns") or {}).items()
    }
    service.select_target_branch(state, branch_id)
    service.parse_simsoft_files(state, file_paths)
    if not state.posting.errors and not state.posting.parsed_df.empty:
        service.load_google_sheet(state)
        service.build_previews(state, include_review_artifacts=include_review_artifacts)
    service.recompute_posting_gate(state)
    return service, state


def preview_payload(service: SimsoftWorkflowService, state: AppState) -> dict[str, Any]:
    lock_reasons = service.recompute_posting_gate(state)
    return {
        "parsedRows": dataframe_records(state.posting.parsed_df),
        "accountsPreviewRows": dataframe_records(state.posting.accounts_preview_df),
        "receiptPreviewRows": dataframe_records(state.posting.receipt_preview_df),
        "dailyPreviewRows": dataframe_records(state.posting.daily_preview_df),
        "scrPreviewRows": dataframe_records(state.posting.scr_preview_df),
        "fullyPaidCashRows": dataframe_records(service.fully_paid_cash_export(state)),
        "scrUpdates": to_jsonable(state.posting.scr_updates),
        "sheetLayouts": to_jsonable(state.posting.sheet_layouts),
        "aiResolver": to_jsonable(state.posting.ai_resolver),
        "errors": to_jsonable(state.posting.errors),
        "lockReasons": to_jsonable(lock_reasons),
        "summary": to_jsonable(service.summary(state)),
        "sheet": {
            "targetBranchId": state.sheet.target_branch_id,
            "targetBranchName": state.sheet.target_branch_name,
            "targetSpreadsheetId": state.sheet.target_spreadsheet_id,
            "activeReceiptTab": state.sheet.active_receipt_tab,
            "activeDailyTab": state.sheet.active_daily_tab,
            "googleReady": state.sheet.google_ready,
            "accountsRowCount": visible_accounts_number(state.sheet.accounts_rows, state.sheet.accounts_headers)
            if state.sheet.accounts_rows and state.sheet.accounts_headers
            else 0,
        },
        "cache": to_jsonable(state.cache.__dict__),
        "performanceTimings": to_jsonable(state.performance_timings),
        "canPost": state.posting.can_post,
        "postLockReason": state.posting.post_lock_reason,
    }


def build_google_previews(payload: dict[str, Any]) -> dict[str, Any]:
    service, state = prepare_preview_state(payload)
    return preview_payload(service, state)


def google_sheet_stats(payload: dict[str, Any]) -> dict[str, Any]:
    branch_id = str(payload.get("branchId", "")).strip()
    branch_index = payload.get("branchIndex") or {}
    if not branch_id:
        raise ValueError("Select target branch first.")
    if not branch_index or branch_id not in branch_index:
        raise ValueError("Folder scan required before updating the selected Google Sheet.")

    if auth_mode_for_payload(payload) == AUTH_MODE_USER_OAUTH:
        service_account_context, service_account_email = {}, ""
    else:
        service_account_context, service_account_email = load_service_account_context()
    auth_context, *_ = state_auth_context(payload, service_account_context, service_account_email)
    branch = branch_index[branch_id]
    spreadsheet_id = str(branch.get("spreadsheet_id") or "").strip()
    if not spreadsheet_id:
        raise ValueError("Selected branch does not have a Google Spreadsheet ID.")

    client = get_gspread_client(auth_context)
    worksheet = client.open_by_key(spreadsheet_id).worksheet(TARGET_TAB)
    rows = worksheet.get_all_values()
    headers = row_headers(rows, ACCOUNTS_HEADER_ROW)
    return {
        "targetBranchId": branch_id,
        "targetBranchName": branch.get("branch_name", ""),
        "targetSpreadsheetId": spreadsheet_id,
        "accountsRowCount": visible_accounts_number(rows, headers),
        "googleReady": True,
    }


def post_google_previews(payload: dict[str, Any]) -> dict[str, Any]:
    confirmation = str(payload.get("confirmation", "")).strip()
    if confirmation != "Continue Posting":
        raise PermissionError("Final confirmation is required before posting.")
    service, state = prepare_preview_state(payload, include_review_artifacts=False)
    ibp_particulars = payload.get("ibpParticulars") or {}
    if not isinstance(ibp_particulars, dict):
        raise ValueError("Invalid IBP particulars.")
    ibp_payment_breakdowns = payload.get("ibpPaymentBreakdowns") or {}
    if not isinstance(ibp_payment_breakdowns, dict):
        raise ValueError("Invalid IBP payment breakdowns.")
    missing_ibp: list[str] = []
    if not state.posting.parsed_df.empty and "is_ibp" in state.posting.parsed_df:
        for row in state.posting.parsed_df.to_dict("records"):
            if not bool(row.get("is_ibp")) or str(row.get("Status", "")).upper() != "PASSED":
                continue
            key = str(row.get("Transaction Key", "")).strip()
            particular = str(ibp_particulars.get(key, "")).strip()
            if not particular:
                missing_ibp.append(str(row.get("OR Number", "")).strip() or str(row.get("Reference", "")).strip())
            breakdown = ibp_payment_breakdowns.get(key, {})
            amount = str(breakdown.get("amount", "") if isinstance(breakdown, dict) else "").strip()
            if key in ibp_payment_breakdowns and not amount:
                missing_ibp.append(str(row.get("OR Number", "")).strip() or str(row.get("Reference", "")).strip())
    if missing_ibp:
        raise ValueError(f"IBP particular is required before posting: {', '.join(missing_ibp)}")
    lock_reasons = service.recompute_posting_gate(state)
    if not state.posting.can_post:
        raise PermissionError(state.posting.post_lock_reason or "Posting is locked.")
    posted_count = service.post(state)
    result = preview_payload(service, state)
    result.update(
        {
            "postedCount": posted_count,
            "postedAt": state.posting.posted_at,
            "lastPostStatus": state.posting.last_post_status,
            "lockReasons": to_jsonable(lock_reasons),
        }
    )
    return result


def duplicate_history_status(_: dict[str, Any]) -> dict[str, Any]:
    ensure_history_file(DUPLICATE_HISTORY_PATH)
    keys = []
    import csv

    with DUPLICATE_HISTORY_PATH.open("r", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("Transaction Key"):
                keys.append(row["Transaction Key"])
    batch_count = 0
    if POSTED_BATCHES_PATH.exists():
        with POSTED_BATCHES_PATH.open("r", newline="", encoding="utf-8") as fh:
            batch_count = sum(1 for _ in csv.DictReader(fh))
    return {
        "duplicateHistoryPath": str(DUPLICATE_HISTORY_PATH),
        "duplicateTransactionCount": len(set(keys)),
        "postedBatchRowCount": batch_count,
    }


def reset_duplicate_history(payload: dict[str, Any]) -> dict[str, Any]:
    confirmation = str(payload.get("confirmation", "")).strip()
    if confirmation != "Reset Duplicate History":
        raise PermissionError("Type Reset Duplicate History before clearing local duplicate history.")
    import csv

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = Path("data/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    backups: list[str] = []
    for source in [DUPLICATE_HISTORY_PATH, POSTED_BATCHES_PATH]:
        if source.exists():
            backup = backup_dir / f"{source.stem}_{timestamp}{source.suffix}"
            shutil.copy2(source, backup)
            backups.append(str(backup))

    with DUPLICATE_HISTORY_PATH.open("w", newline="", encoding="utf-8") as fh:
        csv.DictWriter(fh, fieldnames=HISTORY_COLUMNS).writeheader()
    with POSTED_BATCHES_PATH.open("w", newline="", encoding="utf-8") as fh:
        csv.DictWriter(fh, fieldnames=POSTED_BATCH_COLUMNS).writeheader()
    return {
        **duplicate_history_status({}),
        "backups": backups,
    }


def dispatch_command(payload: dict[str, Any]) -> dict[str, Any]:
    command = payload.get("command")
    if command == "parse_simsoft":
        return parse_simsoft(payload)
    if command == "scan_google_folder":
        return scan_google_folder(payload)
    if command == "build_google_previews":
        return build_google_previews(payload)
    if command == "google_sheet_stats":
        return google_sheet_stats(payload)
    if command == "post_google_previews":
        return post_google_previews(payload)
    if command == "operator_identity":
        return operator_identity(payload)
    if command == "operator_login_google":
        return operator_login_google(payload)
    if command == "operator_logout_google":
        return operator_logout_google(payload)
    if command == "duplicate_history_status":
        return duplicate_history_status(payload)
    if command == "reset_duplicate_history":
        return reset_duplicate_history(payload)
    if command == "ping":
        return {"ok": True}
    raise ValueError(f"Unknown Python bridge command: {command}")


def execute_payload(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        with redirect_stdout(sys.stderr):
            result = dispatch_command(payload)
        return {"ok": True, "result": result}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def run_server() -> int:
    sys.stderr.write("SIMSOFT Python bridge server ready\n")
    sys.stderr.flush()
    for line in sys.stdin:
        raw = line.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
            if payload.get("command") == "shutdown":
                sys.stdout.write(json.dumps({"ok": True, "result": {"shutdown": True}}) + "\n")
                sys.stdout.flush()
                return 0
            response = execute_payload(payload)
        except Exception as exc:
            response = {"ok": False, "error": str(exc)}
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()
    return 0


def main() -> int:
    if "--server" in sys.argv:
        return run_server()
    payload = json.loads(sys.stdin.read() or "{}")
    response = execute_payload(payload)
    sys.stdout.write(json.dumps(response))
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
