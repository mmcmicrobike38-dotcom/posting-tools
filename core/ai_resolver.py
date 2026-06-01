from __future__ import annotations

import json
import os
import re
from decimal import Decimal
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import pandas as pd


AI_RESOLVER_TABS = {"SIMSOFT", "ACCOUNTS", "RECEIPT", "RECIEPT", "DAILY", "1-31", "SCR VS BR"}
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
SAFE_MODEL_NAME = re.compile(r"^[A-Za-z0-9._-]{1,80}$")


def _ai_resolver_enabled() -> bool:
    return (os.getenv("SIMSOFT_ENABLE_AI_RESOLVER") or "").strip().lower() in {"1", "true", "yes", "on"}


def _safe_records(frame: pd.DataFrame, limit: int = 12) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    records = frame.head(limit).to_dict("records")
    return [{str(key): _jsonable(value) for key, value in record.items()} for record in records]


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    try:
        if pd.isna(value) and not isinstance(value, (list, dict, tuple)):
            return ""
    except Exception:
        pass
    if hasattr(value, "item"):
        try:
            return _jsonable(value.item())
        except Exception:
            pass
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value


def _problem_rows(frame: pd.DataFrame, limit: int = 12) -> list[dict[str, Any]]:
    if frame.empty or "Status" not in frame:
        return []
    problem = frame[frame["Status"].astype(str).isin(["ERROR", "DUPLICATE"])]
    return _safe_records(problem, limit)


def _recent_sheet_rows(rows: list[list[Any]], limit: int = 14) -> list[list[Any]]:
    if not rows:
        return []
    trimmed = rows[:4] + rows[-limit:]
    return [[_jsonable(cell) for cell in row[:16]] for row in trimmed]


def build_ai_resolver_context(
    *,
    parsed_df: pd.DataFrame,
    accounts_preview_df: pd.DataFrame,
    receipt_preview_df: pd.DataFrame,
    daily_preview_df: pd.DataFrame,
    scr_preview_df: pd.DataFrame,
    accounts_rows: list[list[Any]],
    accounts_headers: list[str],
    receipt_rows: list[list[Any]],
    receipt_headers: list[str],
    daily_rows: list[list[Any]],
    scr_rows: list[list[Any]],
    scr_updates: list[dict[str, Any]],
    active_receipt_tab: str,
    active_daily_tab: str,
    target_branch_id: str,
    target_branch_name: str,
    errors: list[str],
) -> dict[str, Any]:
    simsoft_problems = _problem_rows(parsed_df)
    account_problems = _problem_rows(accounts_preview_df)
    receipt_problems = _problem_rows(receipt_preview_df)
    daily_problems = _problem_rows(daily_preview_df)
    scr_problems = _problem_rows(scr_preview_df)
    return {
        "targetBranch": {
            "id": target_branch_id,
            "name": target_branch_name,
        },
        "activeTabs": {
            "receipt": active_receipt_tab,
            "daily": active_daily_tab,
        },
        "errors": [str(error) for error in errors if str(error).strip()][:30],
        "simsoftRows": _safe_records(parsed_df, 16),
        "simsoftProblems": simsoft_problems,
        "accountsPreviewProblems": account_problems,
        "receiptPreviewProblems": receipt_problems,
        "dailyPreviewProblems": daily_problems,
        "scrPreviewProblems": scr_problems,
        "accountsHeaders": accounts_headers[:20],
        "receiptHeaders": receipt_headers[:20],
        "accountsSheetSample": _recent_sheet_rows(accounts_rows),
        "receiptSheetSample": _recent_sheet_rows(receipt_rows),
        "dailySheetSample": _recent_sheet_rows(daily_rows),
        "scrSheetSample": _recent_sheet_rows(scr_rows),
        "scrUpdates": [_jsonable(update) for update in scr_updates[:20]],
    }


def _empty_report(status: str, model: str = "", summary: str = "", error: str = "") -> dict[str, Any]:
    return {
        "enabled": status not in {"disabled", "skipped"},
        "status": status,
        "model": model,
        "summary": summary,
        "suggestions": [],
        "warnings": [],
        "error": error,
    }


def _has_ai_work(context: dict[str, Any]) -> bool:
    return bool(
        context.get("simsoftProblems")
        or context.get("accountsPreviewProblems")
        or context.get("receiptPreviewProblems")
        or context.get("dailyPreviewProblems")
        or context.get("scrPreviewProblems")
        or context.get("errors")
    )


def _extract_text(response: dict[str, Any]) -> str:
    candidates = response.get("candidates") or []
    if not candidates:
        return ""
    parts = ((candidates[0].get("content") or {}).get("parts") or [])
    return "\n".join(str(part.get("text", "")) for part in parts if isinstance(part, dict)).strip()


def _parse_json_text(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def _normalize_report(payload: dict[str, Any], model: str) -> dict[str, Any]:
    suggestions = payload.get("suggestions")
    if not isinstance(suggestions, list):
        suggestions = []
    normalized_suggestions: list[dict[str, Any]] = []
    for item in suggestions[:12]:
        if not isinstance(item, dict):
            continue
        tab = str(item.get("tab", "")).strip().upper()
        if tab not in AI_RESOLVER_TABS:
            continue
        confidence_raw = item.get("confidence", 0)
        try:
            confidence = max(0, min(100, int(float(confidence_raw))))
        except Exception:
            confidence = 0
        normalized_suggestions.append(
            {
                "tab": tab,
                "severity": str(item.get("severity") or "review").strip().lower(),
                "rowKey": str(item.get("rowKey") or "").strip(),
                "issue": str(item.get("issue") or "").strip(),
                "suggestion": str(item.get("suggestion") or "").strip(),
                "confidence": confidence,
                "proposedUpdates": item.get("proposedUpdates") if isinstance(item.get("proposedUpdates"), list) else [],
                "reason": str(item.get("reason") or "").strip(),
            }
        )
    warnings = payload.get("warnings")
    if not isinstance(warnings, list):
        warnings = []
    return {
        "enabled": True,
        "status": "ready",
        "model": model,
        "summary": str(payload.get("summary") or "AI resolver review completed.").strip(),
        "suggestions": normalized_suggestions,
        "warnings": [str(warning) for warning in warnings[:8] if str(warning).strip()],
        "error": "",
    }


def resolve_posting_with_gemini(context: dict[str, Any]) -> dict[str, Any]:
    model = (os.getenv("SIMSOFT_GEMINI_MODEL") or DEFAULT_GEMINI_MODEL).strip()
    if not _ai_resolver_enabled():
        return _empty_report("disabled", model, "Set SIMSOFT_ENABLE_AI_RESOLVER=1 and SIMSOFT_GEMINI_API_KEY to enable Gemini posting resolver.")
    if not SAFE_MODEL_NAME.fullmatch(model):
        return _empty_report("error", DEFAULT_GEMINI_MODEL, error="Invalid Gemini model name.")
    api_key = (os.getenv("SIMSOFT_GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        return _empty_report("disabled", model, "Set SIMSOFT_GEMINI_API_KEY to enable Gemini posting resolver.")
    if not _has_ai_work(context):
        return _empty_report("skipped", model, "No posting blocker needed AI review.")

    prompt = {
        "role": "system",
        "task": (
            "You are a SIMSOFT Google Sheet posting resolver. Review SIMSOFT, ACCOUNTS, RECEIPT, DAILY/1-31, and SCR VS BR issues. "
            "Do not invent source data. Do not approve posting. Return JSON only."
        ),
        "outputSchema": {
            "summary": "short plain English summary",
            "suggestions": [
                {
                    "tab": "SIMSOFT, ACCOUNTS, RECEIPT, DAILY, 1-31, or SCR VS BR",
                    "severity": "review|warning|blocker",
                    "rowKey": "Transaction Key, OR number, or account",
                    "issue": "what is uncertain or wrong",
                    "suggestion": "what the operator/app should check or change",
                    "confidence": "0-100 integer",
                    "proposedUpdates": [{"range": "A1 notation if known", "value": "suggested value"}],
                    "reason": "short reason based only on supplied context",
                }
            ],
            "warnings": ["safety notes"],
        },
        "context": context,
    }
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": json.dumps(prompt, ensure_ascii=True)}],
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "response_mime_type": "application/json",
        },
    }
    request = Request(
        GEMINI_ENDPOINT.format(model=model),
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        text = _extract_text(payload)
        if not text:
            return _empty_report("error", model, error="Gemini returned an empty resolver response.")
        return _normalize_report(_parse_json_text(text), model)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return _empty_report("error", model, error=f"Gemini resolver failed: {exc}")
