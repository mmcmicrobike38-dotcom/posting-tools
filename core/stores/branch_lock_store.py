from __future__ import annotations

from typing import Protocol

from core.concurrency import BranchLock, LocalCsvDuplicateAuditStore, branch_lock_key


class BranchLockStore(Protocol):
    def acquire_lock(
        self,
        branch_id: str,
        spreadsheet_id: str,
        operator_email: str,
        batch_id: str,
        operator_name: str = "",
    ) -> BranchLock: ...
    def release_lock(self, lock: BranchLock) -> str: ...
    def is_locked(self, branch_id: str, spreadsheet_id: str) -> bool: ...


class LocalBranchLockStore:
    def __init__(self, backing_store: LocalCsvDuplicateAuditStore | None = None) -> None:
        self.backing_store = backing_store or LocalCsvDuplicateAuditStore()

    def acquire_lock(
        self,
        branch_id: str,
        spreadsheet_id: str,
        operator_email: str,
        batch_id: str,
        operator_name: str = "",
    ) -> BranchLock:
        return self.backing_store.acquire_branch_lock(
            lock_key=branch_lock_key(branch_id, spreadsheet_id),
            batch_id=batch_id,
            operator_email=operator_email,
            operator_name=operator_name,
        )

    def release_lock(self, lock: BranchLock) -> str:
        return self.backing_store.release_branch_lock(lock)

    def is_locked(self, branch_id: str, spreadsheet_id: str) -> bool:
        return self.backing_store.is_branch_locked(branch_lock_key(branch_id, spreadsheet_id))
