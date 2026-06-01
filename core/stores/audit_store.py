from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from core.audit import write_audit_log
from core.settings import DEFAULT_LOG_DIR


class AuditStore(Protocol):
    def write_audit_log(
        self,
        preview_df: pd.DataFrame,
        batch_id: str,
        sheet_url: str,
        source_file: str,
        selected_tabs: list[str],
        auth_metadata: dict[str, Any] | None = None,
    ) -> Path: ...


class LocalAuditStore:
    def __init__(self, log_dir: str | Path = DEFAULT_LOG_DIR) -> None:
        self.log_dir = Path(log_dir)

    def write_audit_log(
        self,
        preview_df: pd.DataFrame,
        batch_id: str,
        sheet_url: str,
        source_file: str,
        selected_tabs: list[str],
        auth_metadata: dict[str, Any] | None = None,
    ) -> Path:
        return write_audit_log(preview_df, batch_id, sheet_url, source_file, selected_tabs, self.log_dir, auth_metadata)
