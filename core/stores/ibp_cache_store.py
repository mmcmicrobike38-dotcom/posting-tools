from __future__ import annotations

from typing import Any, Protocol


class IBPLookupCacheStore(Protocol):
    def get_account_lookup(self, key: str) -> dict[str, Any] | None: ...
    def set_account_lookup(self, key: str, result: dict[str, Any]) -> None: ...
    def get_branch_index(self, spreadsheet_id: str) -> dict[str, Any] | None: ...
    def set_branch_index(self, spreadsheet_id: str, index: dict[str, Any]) -> None: ...
    def clear(self) -> None: ...


class LocalIBPLookupCacheStore:
    """Session-only IBP cache. Intentionally not persisted across days."""

    def __init__(self) -> None:
        self.account_lookup_cache: dict[str, dict[str, Any]] = {}
        self.branch_account_index_cache: dict[str, dict[str, Any]] = {}

    def get_account_lookup(self, key: str) -> dict[str, Any] | None:
        return self.account_lookup_cache.get(key)

    def set_account_lookup(self, key: str, result: dict[str, Any]) -> None:
        self.account_lookup_cache[key] = result

    def get_branch_index(self, spreadsheet_id: str) -> dict[str, Any] | None:
        return self.branch_account_index_cache.get(spreadsheet_id)

    def set_branch_index(self, spreadsheet_id: str, index: dict[str, Any]) -> None:
        self.branch_account_index_cache[spreadsheet_id] = index

    def clear(self) -> None:
        self.account_lookup_cache.clear()
        self.branch_account_index_cache.clear()
