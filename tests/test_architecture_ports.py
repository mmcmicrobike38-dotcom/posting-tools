from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from python_backend.application.events import InMemoryEventBus
from python_backend.models.app_state import AppState
from python_backend.services.workflow_service import SimsoftWorkflowService, TARGET_TAB


class FakeAuditRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def write(
        self,
        preview_df: pd.DataFrame,
        batch_id: str,
        sheet_url: str,
        source_file: str,
        target_tabs: list[str],
        auth_metadata: dict[str, Any],
    ) -> Path:
        self.calls.append(
            {
                "rows": len(preview_df),
                "batch_id": batch_id,
                "sheet_url": sheet_url,
                "source_file": source_file,
                "target_tabs": target_tabs,
                "auth_metadata": auth_metadata,
            }
        )
        return Path("logs/fake-audit.csv")


class FakeSheetsGateway:
    def __init__(self) -> None:
        self.posted: list[tuple[Any, list[dict[str, Any]]]] = []

    def client(self, auth_context: Any) -> Any:
        raise AssertionError("client should not be needed in this unit test")

    def post_updates(self, worksheet: Any, updates: list[dict[str, Any]]) -> None:
        self.posted.append((worksheet, updates))


def test_preview_audit_uses_repository_and_publishes_event():
    event_bus = InMemoryEventBus()
    audit = FakeAuditRepository()
    service = SimsoftWorkflowService(audit_repository=audit, event_bus=event_bus)
    state = AppState()
    state.sheet.target_branch_id = "MMC038"
    state.sheet.target_branch_name = "POZORRUBIO"
    state.sheet.target_spreadsheet_id = "sheet123"
    state.sheet.sheet_url = "https://docs.google.com/spreadsheets/d/sheet123"
    state.sheet.active_receipt_tab = "RECEIPT"
    state.sheet.active_daily_tab = "1-31"
    state.posting.source_file = "simsoft.xlsx"
    state.posting.accounts_preview_df = pd.DataFrame(
        [{"Target Tab": TARGET_TAB, "Status": "PASSED", "Transaction Key": "key1"}]
    )

    path = service.write_preview_audit(state)

    assert path == Path("logs/fake-audit.csv")
    assert audit.calls[0]["target_tabs"] == [TARGET_TAB, "RECEIPT", "1-31", "SCR VS BR"]
    assert event_bus.events[-1].name == "PostingPreviewAuditWritten"
    assert event_bus.events[-1].payload["target_branch_id"] == "MMC038"


def test_sheet_gateway_is_injected_for_posting_writes(monkeypatch):
    import python_backend.services.workflow_service as workflow_service

    event_bus = InMemoryEventBus()
    sheets = FakeSheetsGateway()
    service = SimsoftWorkflowService(sheets_gateway=sheets, event_bus=event_bus)
    state = AppState(test_mode=True, auth_ready=True)
    state.sheet.google_ready = True
    state.sheet.target_branch_id = "MMC038"
    state.sheet.target_spreadsheet_id = "sheet123"
    state.sheet.target_branch_name = "POZORRUBIO"
    state.sheet.sheet_url = "https://docs.google.com/spreadsheets/d/sheet123"
    state.sheet.active_receipt_tab = "RECEIPT"
    state.sheet.active_daily_tab = "1-31"
    state.sheet.accounts_worksheet = "accounts"
    state.sheet.receipt_worksheet = "receipt"
    state.sheet.daily_worksheet = "daily"
    state.sheet.scr_worksheet = "scr"
    state.sheet.accounts_rows = [["ACCOUNT"]]
    state.sheet.receipt_rows = [["TYPE"]]
    state.sheet.daily_rows = [["DATE"]]
    state.sheet.scr_rows = [["SCR DATE"]]
    state.branch_index = {"MMC038": {"spreadsheet_id": "sheet123"}}
    state.cache.preview = "Fresh"
    state.posting.validation_snapshot = service.sheet_snapshot(state)
    state.posting.validation_snapshot_id = "snapshot"
    state.posting.can_post = True
    state.posting.parsed_df = pd.DataFrame(
        [{"Status": "PASSED", "Transaction Key": "key1", "Account Name": "A"}]
    )
    state.posting.accounts_preview_df = pd.DataFrame(
        [{"Target Tab": TARGET_TAB, "Status": "PASSED", "Transaction Key": "key1"}]
    )
    state.posting.receipt_preview_df = pd.DataFrame(
        [{"Target Tab": "RECIEPT", "Status": "PASSED", "Transaction Key": "key1"}]
    )
    state.posting.daily_preview_df = pd.DataFrame(
        [{"Target Tab": "1-31", "Status": "PASSED", "Transaction Key": "key1"}]
    )
    state.posting.scr_preview_df = pd.DataFrame(
        [{"Target Tab": "SCR VS BR", "Status": "PASSED", "Transaction Key": "key1"}]
    )
    state.posting.scr_updates = [{"row": 1, "col": 1, "value": "scr"}]

    monkeypatch.setattr(workflow_service, "prepare_sheet_updates", lambda *args: [{"row": 1, "col": 1, "value": "account"}])
    monkeypatch.setattr(workflow_service, "prepare_daily_collection_updates", lambda *args: ([{"row": 1, "col": 2, "value": "daily-account"}], []))
    monkeypatch.setattr(workflow_service, "prepare_daily_sheet_updates", lambda *args: ([{"row": 1, "col": 1, "value": "daily"}], []))
    monkeypatch.setattr(workflow_service, "prepare_receipt_updates", lambda *args: [{"row": 1, "col": 1, "value": "receipt"}])
    monkeypatch.setattr(service, "write_final_audit", lambda state: None)

    posted_count = service.post(state)

    assert posted_count == 0
    assert [worksheet for worksheet, _ in sheets.posted] == ["accounts", "receipt", "daily", "scr"]
    assert event_bus.events[-1].name == "PostingPreviewPosted"
    assert event_bus.events[-1].payload["target_branch_id"] == "MMC038"
