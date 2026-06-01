from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from core.audit import write_audit_log
from core.concurrency import BranchLock, DuplicateAuditStore, branch_lock_key
from core.google_sheets import get_gspread_client, post_to_google_sheet


class GoogleSheetsGateway(Protocol):
    def client(self, auth_context: Any) -> Any:
        ...

    def post_updates(self, worksheet: Any, updates: list[dict[str, Any]]) -> None:
        ...


class DefaultGoogleSheetsGateway:
    def client(self, auth_context: Any) -> Any:
        return get_gspread_client(auth_context)

    def post_updates(self, worksheet: Any, updates: list[dict[str, Any]]) -> None:
        post_to_google_sheet(worksheet, updates)


class AuditRepository(Protocol):
    def write(
        self,
        preview_df: pd.DataFrame,
        batch_id: str,
        sheet_url: str,
        source_file: str,
        target_tabs: list[str],
        auth_metadata: dict[str, Any],
    ) -> Path:
        ...


class LocalCsvAuditRepository:
    def write(
        self,
        preview_df: pd.DataFrame,
        batch_id: str,
        sheet_url: str,
        source_file: str,
        target_tabs: list[str],
        auth_metadata: dict[str, Any],
    ) -> Path:
        return write_audit_log(
            preview_df,
            batch_id,
            sheet_url,
            source_file,
            target_tabs,
            auth_metadata=auth_metadata,
        )


@dataclass
class PostingTransaction:
    lock: BranchLock | None = None
    recorded_count: int = 0


class PostingTransactionManager:
    def __init__(self, duplicate_store: DuplicateAuditStore) -> None:
        self.duplicate_store = duplicate_store

    def batch_exists(self, batch_id: str) -> bool:
        return self.duplicate_store.batch_exists(batch_id)

    def existing_transaction_keys(self, keys: list[str]) -> set[str]:
        return self.duplicate_store.existing_transaction_keys(keys)

    def acquire_branch_lock(
        self,
        target_branch_id: str,
        target_spreadsheet_id: str,
        batch_id: str,
        operator_email: str,
        operator_name: str,
    ) -> BranchLock:
        return self.duplicate_store.acquire_branch_lock(
            lock_key=branch_lock_key(target_branch_id, target_spreadsheet_id),
            batch_id=batch_id,
            operator_email=operator_email,
            operator_name=operator_name,
        )

    def release_branch_lock(self, lock: BranchLock) -> str:
        return self.duplicate_store.release_branch_lock(lock)

    def record_posted_batch(
        self,
        batch_id: str,
        operator_email: str,
        target_branch_id: str,
        target_tabs: list[str],
        records: list[dict[str, Any]],
        posted_at: str,
    ) -> int:
        return self.duplicate_store.record_posted_batch(
            batch_id=batch_id,
            operator_email=operator_email,
            target_branch_id=target_branch_id,
            target_tabs=target_tabs,
            records=records,
            posted_at=posted_at,
        )
