from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Protocol

from core.audit import append_duplicate_history, load_duplicate_history
from core.settings import DEFAULT_DUPLICATE_HISTORY_PATH


class DuplicateStore(Protocol):
    def transaction_keys(self) -> set[str]: ...
    def has_transaction_key(self, key: str) -> bool: ...
    def add_transaction_key(self, key: str, metadata: dict[str, Any]) -> None: ...
    def add_transaction_keys(self, records: Iterable[dict[str, Any]], batch_id: str, target_tabs: list[str]) -> int: ...
    def existing_transaction_keys(self, transaction_keys: Iterable[str]) -> set[str]: ...
    def refresh(self) -> set[str]: ...


class LocalDuplicateStore:
    def __init__(self, history_path: str | Path = DEFAULT_DUPLICATE_HISTORY_PATH) -> None:
        self.history_path = Path(history_path)
        self._keys: set[str] | None = None

    def transaction_keys(self) -> set[str]:
        if self._keys is None:
            self._keys = load_duplicate_history(self.history_path)
        return set(self._keys)

    def refresh(self) -> set[str]:
        self._keys = load_duplicate_history(self.history_path)
        return set(self._keys)

    def has_transaction_key(self, key: str) -> bool:
        return bool(key) and key in self.transaction_keys()

    def existing_transaction_keys(self, transaction_keys: Iterable[str]) -> set[str]:
        known = self.transaction_keys()
        return {key for key in transaction_keys if key and key in known}

    def add_transaction_key(self, key: str, metadata: dict[str, Any]) -> None:
        if not key or self.has_transaction_key(key):
            return
        record = {"Status": "PASSED", "Transaction Key": key, **metadata}
        self.add_transaction_keys([record], str(metadata.get("Batch ID", "")), str(metadata.get("Target Tabs", "")).split(", "))

    def add_transaction_keys(self, records: Iterable[dict[str, Any]], batch_id: str, target_tabs: list[str]) -> int:
        count = append_duplicate_history(records, batch_id, target_tabs, self.history_path)
        if self._keys is not None:
            self._keys.update(
                row.get("Transaction Key", "")
                for row in records
                if row.get("Status") == "PASSED" and row.get("Transaction Key")
            )
        return count
