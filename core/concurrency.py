from __future__ import annotations

import csv
import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .audit import append_duplicate_history, ensure_directories, load_duplicate_history
from .settings import DEFAULT_DUPLICATE_HISTORY_PATH, DEFAULT_POSTED_BATCHES_PATH, DEFAULT_POSTING_LOCKS_PATH


LOCKED_BRANCH_MESSAGE = "This branch is currently being posted by another operator. Please wait and refresh."
DEFAULT_LOCK_TIMEOUT_SECONDS = 15 * 60
POSTED_BATCH_COLUMNS = [
    "batch_id",
    "operator_email",
    "target_branch_id",
    "target_tab",
    "transaction_key",
    "posted_at",
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat(timespec="seconds")


def parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def branch_lock_key(target_branch_id: str, target_spreadsheet_id: str) -> str:
    return f"{target_branch_id.strip().upper()}|{target_spreadsheet_id.strip()}"


@dataclass
class BranchLock:
    key: str
    token: str
    batch_id: str
    operator_email: str
    operator_name: str
    acquired_at: str
    expires_at: str


class BranchLockError(RuntimeError):
    pass


class DuplicateAuditStore:
    shared_warning = (
        "Local duplicate_history.csv protects this PC only. For multi-PC operation, configure a shared duplicate/audit "
        "store such as a central audit Google Sheet, shared Drive file, or database."
    )

    def transaction_keys(self) -> set[str]:
        raise NotImplementedError

    def batch_exists(self, batch_id: str) -> bool:
        raise NotImplementedError

    def existing_transaction_keys(self, transaction_keys: Iterable[str]) -> set[str]:
        known = self.transaction_keys()
        return {key for key in transaction_keys if key and key in known}

    def acquire_branch_lock(
        self,
        *,
        lock_key: str,
        batch_id: str,
        operator_email: str,
        operator_name: str,
        timeout_seconds: int = DEFAULT_LOCK_TIMEOUT_SECONDS,
    ) -> BranchLock:
        raise NotImplementedError

    def release_branch_lock(self, lock: BranchLock) -> str:
        raise NotImplementedError

    def is_branch_locked(self, lock_key: str) -> bool:
        raise NotImplementedError

    def record_posted_batch(
        self,
        *,
        batch_id: str,
        operator_email: str,
        target_branch_id: str,
        target_tabs: list[str],
        records: Iterable[dict[str, Any]],
        posted_at: str,
    ) -> int:
        raise NotImplementedError


class LocalCsvDuplicateAuditStore(DuplicateAuditStore):
    def __init__(
        self,
        history_path: str | Path = DEFAULT_DUPLICATE_HISTORY_PATH,
        batch_path: str | Path = DEFAULT_POSTED_BATCHES_PATH,
        lock_state_path: str | Path = DEFAULT_POSTING_LOCKS_PATH,
    ) -> None:
        self.history_path = Path(history_path)
        self.batch_path = Path(batch_path)
        self.lock_state_path = Path(lock_state_path)
        self.lock_guard_path = self.lock_state_path.with_suffix(self.lock_state_path.suffix + ".guard")
        ensure_directories()

    @contextmanager
    def _exclusive_guard(self):
        self.lock_state_path.parent.mkdir(parents=True, exist_ok=True)
        start = time.monotonic()
        fd: int | None = None
        while fd is None:
            try:
                fd = os.open(str(self.lock_guard_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode("utf-8"))
            except FileExistsError:
                stale = False
                try:
                    stale = time.time() - self.lock_guard_path.stat().st_mtime > 30
                except OSError:
                    stale = False
                if stale:
                    try:
                        self.lock_guard_path.unlink()
                    except OSError:
                        pass
                    continue
                if time.monotonic() - start > 10:
                    raise BranchLockError(LOCKED_BRANCH_MESSAGE)
                time.sleep(0.05)
        try:
            yield
        finally:
            if fd is not None:
                os.close(fd)
            try:
                self.lock_guard_path.unlink()
            except OSError:
                pass

    def _read_locks(self) -> dict[str, Any]:
        if not self.lock_state_path.exists():
            return {}
        try:
            return json.loads(self.lock_state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _write_locks(self, locks: dict[str, Any]) -> None:
        self.lock_state_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_state_path.write_text(json.dumps(locks, indent=2, sort_keys=True), encoding="utf-8")

    def _ensure_batch_file(self) -> Path:
        ensure_directories()
        self.batch_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.batch_path.exists():
            with self.batch_path.open("w", newline="", encoding="utf-8") as fh:
                csv.DictWriter(fh, fieldnames=POSTED_BATCH_COLUMNS).writeheader()
        return self.batch_path

    def transaction_keys(self) -> set[str]:
        return load_duplicate_history(self.history_path)

    def batch_exists(self, batch_id: str) -> bool:
        batch_path = self._ensure_batch_file()
        with batch_path.open("r", newline="", encoding="utf-8") as fh:
            return any(row.get("batch_id") == batch_id for row in csv.DictReader(fh))

    def acquire_branch_lock(
        self,
        *,
        lock_key: str,
        batch_id: str,
        operator_email: str,
        operator_name: str,
        timeout_seconds: int = DEFAULT_LOCK_TIMEOUT_SECONDS,
    ) -> BranchLock:
        token = f"{batch_id}:{os.getpid()}:{time.time_ns()}"
        acquired_at_dt = utc_now()
        expires_at_dt = acquired_at_dt + timedelta(seconds=timeout_seconds)
        with self._exclusive_guard():
            locks = self._read_locks()
            current = locks.get(lock_key)
            if current:
                expires_at = parse_iso_datetime(str(current.get("expires_at", "")))
                if expires_at and expires_at > acquired_at_dt:
                    raise BranchLockError(LOCKED_BRANCH_MESSAGE)
            lock = BranchLock(
                key=lock_key,
                token=token,
                batch_id=batch_id,
                operator_email=operator_email,
                operator_name=operator_name,
                acquired_at=acquired_at_dt.isoformat(timespec="seconds"),
                expires_at=expires_at_dt.isoformat(timespec="seconds"),
            )
            locks[lock_key] = lock.__dict__
            self._write_locks(locks)
            return lock

    def release_branch_lock(self, lock: BranchLock) -> str:
        released_at = iso_now()
        with self._exclusive_guard():
            locks = self._read_locks()
            current = locks.get(lock.key)
            if current and current.get("token") == lock.token:
                del locks[lock.key]
                self._write_locks(locks)
        return released_at

    def is_branch_locked(self, lock_key: str) -> bool:
        now = utc_now()
        with self._exclusive_guard():
            locks = self._read_locks()
            current = locks.get(lock_key)
            if not current:
                return False
            expires_at = parse_iso_datetime(str(current.get("expires_at", "")))
            if expires_at and expires_at > now:
                return True
            locks.pop(lock_key, None)
            self._write_locks(locks)
            return False

    def record_posted_batch(
        self,
        *,
        batch_id: str,
        operator_email: str,
        target_branch_id: str,
        target_tabs: list[str],
        records: Iterable[dict[str, Any]],
        posted_at: str,
    ) -> int:
        record_list = [record for record in records if record.get("Status") == "PASSED"]
        if self.batch_exists(batch_id):
            return 0
        existing = self.existing_transaction_keys(record.get("Transaction Key", "") for record in record_list)
        new_records = [record for record in record_list if record.get("Transaction Key") not in existing]
        count = append_duplicate_history(new_records, batch_id, target_tabs, self.history_path)
        batch_path = self._ensure_batch_file()
        with batch_path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=POSTED_BATCH_COLUMNS)
            for record in new_records:
                transaction_key = record.get("Transaction Key", "")
                for target_tab in target_tabs:
                    writer.writerow(
                        {
                            "batch_id": batch_id,
                            "operator_email": operator_email,
                            "target_branch_id": target_branch_id,
                            "target_tab": target_tab,
                            "transaction_key": transaction_key,
                            "posted_at": posted_at,
                        }
                    )
        return count
