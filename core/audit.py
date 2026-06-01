from __future__ import annotations

import csv
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .parser import format_decimal, normalize_text
from .settings import DEFAULT_DUPLICATE_HISTORY_PATH, DEFAULT_LOG_DIR


HISTORY_COLUMNS = [
    "Transaction Key",
    "Account Name",
    "Date",
    "Reference",
    "OR Number",
    "Amount",
    "Interest",
    "Rebate",
    "Actual Collection",
    "Target Tabs",
    "Batch ID",
    "Posted At",
]

AUDIT_COLUMNS = [
    "Batch ID",
    "Generated At",
    "Google Sheet URL",
    "Source File",
    "Selected Target Tabs",
    "Target Tab",
    "Action",
    "Account Name",
    "Date",
    "Reference",
    "OR Number",
    "Amount",
    "Interest",
    "Rebate",
    "Actual Collection",
    "Balance",
    "Status",
    "Issue",
    "Transaction Key",
    "is_ibp",
    "ibp_account_no",
    "ibp_source_branch_id",
    "ibp_resolved_customer",
    "ibp_lookup_status",
    "is_other_payment",
    "other_payment_accounts_entry",
    "target_branch_id",
    "target_branch_name",
    "target_spreadsheet_id",
    "branch_lock_id",
    "validation_snapshot_id",
    "preview_generated_at",
    "confirmation_method",
    "auth_mode",
    "google_actor_email",
    "operator_email",
    "posted_by_email",
    "posted_by_google_user",
    "token_user_email",
    "operator_name",
    "started_at",
    "posted_at",
    "lock_acquired_at",
    "lock_released_at",
    "row_count",
    "posted_tabs",
    "errors",
    "duplicate_count",
    "previous_or",
    "new_or",
    "placement_type",
    "reason",
    "changed_by",
    "changed_at",
    "branch",
    "collection_date",
]


def ensure_directories() -> None:
    Path(DEFAULT_LOG_DIR).mkdir(parents=True, exist_ok=True)
    Path(DEFAULT_DUPLICATE_HISTORY_PATH).parent.mkdir(parents=True, exist_ok=True)
    Path("data").mkdir(exist_ok=True)


def new_batch_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]


def ensure_history_file(path: str | Path = DEFAULT_DUPLICATE_HISTORY_PATH) -> Path:
    ensure_directories()
    history_path = Path(path)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    if not history_path.exists():
        with history_path.open("w", newline="", encoding="utf-8") as fh:
            csv.DictWriter(fh, fieldnames=HISTORY_COLUMNS).writeheader()
    return history_path


def load_duplicate_history(path: str | Path = DEFAULT_DUPLICATE_HISTORY_PATH) -> set[str]:
    history_path = ensure_history_file(path)
    with history_path.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return {row["Transaction Key"] for row in reader if row.get("Transaction Key")}


def append_duplicate_history(records: Iterable[dict[str, Any]], batch_id: str, target_tabs: list[str] | None = None, path: str | Path = DEFAULT_DUPLICATE_HISTORY_PATH) -> int:
    history_path = ensure_history_file(path)
    posted_at = datetime.now().isoformat(timespec="seconds")
    count = 0
    with history_path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=HISTORY_COLUMNS)
        for record in records:
            if record.get("Status") != "PASSED":
                continue
            writer.writerow(
                {
                    "Transaction Key": record.get("Transaction Key", ""),
                    "Account Name": record.get("Account Name", ""),
                    "Date": record.get("Date", ""),
                    "Reference": record.get("Reference", ""),
                    "OR Number": record.get("OR Number", ""),
                    "Amount": format_decimal(record.get("Amount", "0")),
                    "Interest": format_decimal(record.get("Interest", "0")),
                    "Rebate": format_decimal(record.get("Rebate", "0")),
                    "Actual Collection": format_decimal(record.get("Actual Collection", "0")),
                    "Target Tabs": ", ".join(target_tabs or []),
                    "Batch ID": batch_id,
                    "Posted At": posted_at,
                }
            )
            count += 1
    return count


def write_audit_log(
    preview_df: pd.DataFrame,
    batch_id: str,
    sheet_url: str,
    source_file: str,
    selected_tabs: list[str],
    log_dir: str | Path = DEFAULT_LOG_DIR,
    auth_metadata: dict[str, Any] | None = None,
) -> Path:
    ensure_directories()
    generated_at = datetime.now().isoformat(timespec="seconds")
    log_path = Path(log_dir) / f"audit_{batch_id}.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    auth_metadata = auth_metadata or {}
    with log_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=AUDIT_COLUMNS)
        writer.writeheader()
        for row in preview_df.to_dict("records"):
            writer.writerow(
                {
                    "Batch ID": batch_id,
                    "Generated At": generated_at,
                    "Google Sheet URL": sheet_url,
                    "Source File": source_file,
                    "Selected Target Tabs": ", ".join(selected_tabs),
                    "Target Tab": row.get("Target Tab", ""),
                    "Action": row.get("Audit Action", "") or ("PREVIEW" if row.get("Status") != "PASSED" else "READY"),
                    "Account Name": row.get("Account Name", ""),
                    "Date": row.get("Date", ""),
                    "Reference": row.get("Reference", ""),
                    "OR Number": row.get("OR Number", ""),
                    "Amount": normalize_text(row.get("Amount", "")),
                    "Interest": normalize_text(row.get("Interest", "")),
                    "Rebate": normalize_text(row.get("Rebate", "")),
                    "Actual Collection": normalize_text(row.get("Actual Collection", "")),
                    "Balance": normalize_text(row.get("Balance", "")),
                    "Status": row.get("Status", ""),
                    "Issue": row.get("Issue", ""),
                    "Transaction Key": row.get("Transaction Key", ""),
                    "is_ibp": row.get("is_ibp", ""),
                    "ibp_account_no": row.get("ibp_account_no", ""),
                    "ibp_source_branch_id": row.get("ibp_source_branch_id", ""),
                    "ibp_resolved_customer": row.get("ibp_resolved_customer", ""),
                    "ibp_lookup_status": row.get("ibp_lookup_status", ""),
                    "is_other_payment": row.get("is_other_payment", ""),
                    "other_payment_accounts_entry": row.get("other_payment_accounts_entry", ""),
                    "target_branch_id": row.get("target_branch_id", ""),
                    "target_branch_name": row.get("target_branch_name", ""),
                    "target_spreadsheet_id": row.get("target_spreadsheet_id", ""),
                    "branch_lock_id": auth_metadata.get("branch_lock_id", ""),
                    "validation_snapshot_id": auth_metadata.get("validation_snapshot_id", ""),
                    "preview_generated_at": auth_metadata.get("preview_generated_at", ""),
                    "confirmation_method": auth_metadata.get("confirmation_method", ""),
                    "auth_mode": auth_metadata.get("auth_mode", ""),
                    "google_actor_email": auth_metadata.get("google_actor_email", ""),
                    "operator_email": auth_metadata.get("operator_email", ""),
                    "posted_by_email": auth_metadata.get("posted_by_email", ""),
                    "posted_by_google_user": auth_metadata.get("posted_by_google_user", ""),
                    "token_user_email": auth_metadata.get("token_user_email", ""),
                    "operator_name": auth_metadata.get("operator_name", ""),
                    "started_at": auth_metadata.get("started_at", ""),
                    "posted_at": auth_metadata.get("posted_at", ""),
                    "lock_acquired_at": auth_metadata.get("lock_acquired_at", ""),
                    "lock_released_at": auth_metadata.get("lock_released_at", ""),
                    "row_count": auth_metadata.get("row_count", ""),
                    "posted_tabs": auth_metadata.get("posted_tabs", ""),
                    "errors": auth_metadata.get("errors", ""),
                    "duplicate_count": auth_metadata.get("duplicate_count", ""),
                    "previous_or": row.get("previous_or", ""),
                    "new_or": row.get("new_or", ""),
                    "placement_type": row.get("placement_type", ""),
                    "reason": row.get("reason", ""),
                    "changed_by": auth_metadata.get("operator_email", "") or auth_metadata.get("posted_by_email", ""),
                    "changed_at": generated_at,
                    "branch": row.get("target_branch_name", "") or auth_metadata.get("target_branch_name", ""),
                    "collection_date": row.get("collection_date", row.get("SCR DATE", "")),
                }
            )
    return log_path
