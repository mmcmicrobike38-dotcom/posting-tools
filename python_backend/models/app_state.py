from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.google_sheets import AUTH_MODE_SERVICE_ACCOUNT


def empty_dataframe():
    import pandas as pd

    return pd.DataFrame()


@dataclass
class GoogleSheetState:
    sheet_url: str = ""
    target_branch_id: str = ""
    target_branch_name: str = ""
    target_spreadsheet_id: str = ""
    accounts_worksheet: Any = None
    accounts_rows: list[list[Any]] = field(default_factory=list)
    accounts_headers: list[str] = field(default_factory=list)
    receipt_worksheet: Any = None
    receipt_rows: list[list[Any]] = field(default_factory=list)
    receipt_headers: list[str] = field(default_factory=list)
    daily_worksheet: Any = None
    daily_rows: list[list[Any]] = field(default_factory=list)
    scr_worksheet: Any = None
    scr_rows: list[list[Any]] = field(default_factory=list)
    active_receipt_tab: str = "RECEIPT"
    active_daily_tab: str = "1-31"
    google_ready: bool = False


@dataclass
class PostingState:
    parsed_df: Any = field(default_factory=empty_dataframe)
    accounts_preview_df: Any = field(default_factory=empty_dataframe)
    receipt_preview_df: Any = field(default_factory=empty_dataframe)
    daily_preview_df: Any = field(default_factory=empty_dataframe)
    scr_preview_df: Any = field(default_factory=empty_dataframe)
    scr_updates: list[dict[str, Any]] = field(default_factory=list)
    sheet_layouts: dict[str, Any] = field(default_factory=dict)
    ai_resolver: dict[str, Any] = field(default_factory=dict)
    ibp_particulars: dict[str, str] = field(default_factory=dict)
    ibp_payment_breakdowns: dict[str, dict[str, str]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    source_file: str = ""
    can_post: bool = False
    post_lock_reason: str = ""
    batch_id: str = ""
    validation_snapshot: str = ""
    validation_snapshot_id: str = ""
    validated_at: str = ""
    lock_acquired_at: str = ""
    lock_released_at: str = ""
    posted_at: str = ""
    last_post_status: str = ""
    posted_target_tabs: list[str] = field(default_factory=list)
    duplicate_count: int = 0
    row_count: int = 0


@dataclass
class CacheState:
    branch_folder: str = "Not Scanned"
    simsoft_parse: str = "Needs Upload"
    preview: str = "Stale"
    target_sheet: str = "Needs Revalidation"
    branch_sheet_count: int = 0
    branch_scan_duration: float = 0.0
    branch_duplicate_warnings: list[str] = field(default_factory=list)


@dataclass
class AppState:
    auth_mode: str = AUTH_MODE_SERVICE_ACCOUNT
    auth_ready: bool = False
    auth_context: Any | None = None
    current_user_email: str = ""
    current_user_name: str = ""
    token_user_email: str = ""
    service_account_email: str = ""
    operator_name: str = ""
    branch_folder_url: str = ""
    branch_index: dict[str, dict[str, Any]] = field(default_factory=dict)
    simsoft_file_path: Path | None = None
    test_mode: bool = False
    sheet: GoogleSheetState = field(default_factory=GoogleSheetState)
    posting: PostingState = field(default_factory=PostingState)
    cache: CacheState = field(default_factory=CacheState)
    performance_timings: dict[str, float] = field(default_factory=dict)
    multi_user_warning: str = ""
