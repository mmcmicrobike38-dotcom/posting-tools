from __future__ import annotations

import os

ENABLE_LIVE_POSTING = True

DEFAULT_DUPLICATE_HISTORY_PATH = os.getenv("SIMSOFT_DUPLICATE_HISTORY_PATH", "data/duplicate_history.csv")
DEFAULT_POSTED_BATCHES_PATH = os.getenv("SIMSOFT_POSTED_BATCHES_PATH", "data/posted_batches.csv")
DEFAULT_POSTING_LOCKS_PATH = os.getenv("SIMSOFT_POSTING_LOCKS_PATH", "data/posting_locks.json")
DEFAULT_LOG_DIR = os.getenv("SIMSOFT_LOG_DIR", "logs")
