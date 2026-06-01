from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Protocol


class BranchIndexStore(Protocol):
    def get(self, cache_key: str) -> dict[str, dict[str, Any]] | None: ...
    def set(self, cache_key: str, branch_index: dict[str, dict[str, Any]]) -> None: ...
    def invalidate(self, cache_key: str | None = None) -> None: ...


class LocalBranchIndexStore:
    def __init__(self, path: str | Path = "data/cache/branch_index.json", ttl_seconds: int = 12 * 60 * 60) -> None:
        self.path = Path(path)
        self.ttl_seconds = ttl_seconds

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def get(self, cache_key: str) -> dict[str, dict[str, Any]] | None:
        entry = self._read().get(cache_key)
        if not entry:
            return None
        if time.time() - float(entry.get("cached_at", 0)) > self.ttl_seconds:
            return None
        branch_index = entry.get("branch_index")
        return branch_index if isinstance(branch_index, dict) else None

    def set(self, cache_key: str, branch_index: dict[str, dict[str, Any]]) -> None:
        payload = self._read()
        payload[cache_key] = {"cached_at": time.time(), "branch_index": branch_index}
        self._write(payload)

    def invalidate(self, cache_key: str | None = None) -> None:
        if cache_key is None:
            if self.path.exists():
                self._write({})
            return
        payload = self._read()
        payload.pop(cache_key, None)
        self._write(payload)
