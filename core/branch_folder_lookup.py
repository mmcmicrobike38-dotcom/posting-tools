from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen

from google.auth.transport.requests import Request as AuthRequest

from .google_sheets import AUTH_MODE_USER_OAUTH, get_credentials_for_auth_context, google_actor_email, retry_google_operation
from .parser import normalize_text

DRIVE_FILE_MIME_TYPE = "application/vnd.google-apps.spreadsheet"
DRIVE_SHORTCUT_MIME_TYPE = "application/vnd.google-apps.shortcut"
DRIVE_API_FILES_URL = "https://www.googleapis.com/drive/v3/files"

FOLDER_ID_PATTERNS = [
    r"drive.google.com/drive/folders/([a-zA-Z0-9_-]+)",
    r"drive.google.com/open\?id=([a-zA-Z0-9_-]+)",
    r"folders/([a-zA-Z0-9_-]+)",
]

BRANCH_ID_PATTERN = re.compile(r"(MMC\d{3})", re.IGNORECASE)
BRANCH_NAME_PATTERN = re.compile(r"^(MMC\d{3})\s*[-_]\s*(.+?)(?:\s+REALTIME.*)?$", re.IGNORECASE)


def extract_drive_folder_id(folder_link: str) -> str:
    text = normalize_text(folder_link)
    if "docs.google.com/spreadsheets/" in text:
        raise ValueError("Paste the Google Drive folder link that contains all branch sheets, not an individual Google Sheet link.")
    for pattern in FOLDER_ID_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    if re.fullmatch(r"[a-zA-Z0-9_-]{20,}", text):
        return text
    raise ValueError("Could not extract a Google Drive folder ID from the link.")


def _auth_label(auth_context: Any) -> str:
    if isinstance(auth_context, dict):
        return auth_context.get("auth_mode", "Service Account")
    return "Service Account"


def _normalize_drive_file_metadata(file_info: dict[str, Any]) -> dict[str, Any] | None:
    mime_type = file_info.get("mimeType", "")
    if mime_type == DRIVE_FILE_MIME_TYPE:
        return file_info
    if mime_type != DRIVE_SHORTCUT_MIME_TYPE:
        return None
    shortcut = file_info.get("shortcutDetails") or {}
    if shortcut.get("targetMimeType") != DRIVE_FILE_MIME_TYPE:
        return None
    normalized = dict(file_info)
    normalized["shortcut_id"] = file_info.get("id", "")
    normalized["id"] = shortcut.get("targetId", "")
    normalized["mimeType"] = DRIVE_FILE_MIME_TYPE
    normalized["is_shortcut"] = True
    return normalized if normalized["id"] else None


def _drive_files_in_folder(auth_context: Any, folder_id: str) -> list[dict[str, Any]]:
    try:
        credentials = get_credentials_for_auth_context(
            auth_context,
            scopes=["https://www.googleapis.com/auth/drive.readonly", "https://www.googleapis.com/auth/spreadsheets.readonly"],
        )
        if not credentials.valid:
            credentials.refresh(AuthRequest())
        
        actor_email = google_actor_email(auth_context) or "unknown"
        query = (
            f"'{folder_id}' in parents and "
            f"(mimeType = '{DRIVE_FILE_MIME_TYPE}' or mimeType = '{DRIVE_SHORTCUT_MIME_TYPE}') and "
            "trashed = false"
        )
        params = {
            "q": query,
            "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,webViewLink,shortcutDetails/targetId,shortcutDetails/targetMimeType)",
            "pageSize": "1000",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        files: list[dict[str, Any]] = []
        page_token = ""
        while True:
            page_params = dict(params)
            if page_token:
                page_params["pageToken"] = page_token
            url = f"{DRIVE_API_FILES_URL}?{urlencode(page_params, safe="'()")}"  # preserve quotes and parentheses
            request = UrlRequest(url, headers={"Authorization": f"Bearer {credentials.token}"})

            def read_payload():
                with urlopen(request, timeout=20) as response:
                    return json.load(response)

            payload = retry_google_operation(read_payload)
            for item in payload.get("files", []):
                normalized = _normalize_drive_file_metadata(item)
                if normalized is not None:
                    files.append(normalized)
            page_token = payload.get("nextPageToken", "")
            if not page_token:
                return files
    except Exception as exc:
        error_msg = str(exc)
        actor_email = google_actor_email(auth_context) or "unknown"
        if _auth_label(auth_context) == AUTH_MODE_USER_OAUTH:
            raise ValueError(
                "The signed-in Google account does not have access to this branch folder. "
                f"Signed-in account: {actor_email}. Error: {error_msg}"
            ) from exc
        raise ValueError(
            f"Drive API error scanning folder {folder_id}. "
            f"Service account: {actor_email}. "
            f"Make sure this service account has access to the folder and Google Drive API is enabled. "
            f"Error: {error_msg}"
        ) from exc


def detect_branch_id_from_filename(filename: str) -> str | None:
    text = normalize_text(filename)
    match = BRANCH_ID_PATTERN.search(text)
    if not match:
        return None
    return match.group(1).upper()


def _detect_branch_name_from_filename(filename: str) -> str:
    text = normalize_text(filename)
    match = BRANCH_NAME_PATTERN.match(text)
    if match:
        branch_name = match.group(2).strip()
        return re.sub(r"\s+REALTIME.*$", "", branch_name, flags=re.IGNORECASE).strip()
    return text


def build_branch_index(files: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for file_info in files:
        filename = file_info.get("name", "")
        spreadsheet_id = file_info.get("id", "")
        branch_id = detect_branch_id_from_filename(filename)
        branch_name = _detect_branch_name_from_filename(filename)
        if not branch_id:
            continue
        entry = {
            "branch_id": branch_id,
            "branch_name": branch_name,
            "spreadsheet_id": spreadsheet_id,
            "file_name": filename,
            "filename": filename,
            "mime_type": file_info.get("mimeType", ""),
            "modified_time": file_info.get("modifiedTime", ""),
            "web_view_link": file_info.get("webViewLink", ""),
            "shortcut_id": file_info.get("shortcut_id", ""),
            "is_shortcut": bool(file_info.get("is_shortcut")),
            "status": "OK",
        }
        if branch_id not in index:
            index[branch_id] = entry
            index[branch_id]["matching_files"] = [entry.copy()]
        else:
            index[branch_id]["matching_files"].append(entry.copy())
            index[branch_id]["status"] = "MULTIPLE_MATCHES"
            index[branch_id]["issue"] = "Multiple files for this branch ID"
            index[branch_id]["matching_file_names"] = [item["file_name"] for item in index[branch_id]["matching_files"]]
    return index


def scan_branch_folder(auth_context: Any, folder_id: str) -> dict[str, dict[str, Any]]:
    files = _drive_files_in_folder(auth_context, folder_id)
    return build_branch_index(files)


def scan_branch_folder_metadata(auth_context: Any, folder_id: str) -> list[dict[str, Any]]:
    return _drive_files_in_folder(auth_context, folder_id)


def diagnose_folder_access(auth_context: Any, folder_id: str) -> dict[str, str]:
    """Diagnose why folder access might be failing."""
    auth_mode = _auth_label(auth_context)
    actor_email = google_actor_email(auth_context) or "unknown"
    diagnosis = {
        "service_account_email": actor_email,
        "google_actor_email": actor_email,
        "auth_mode": auth_mode,
        "folder_id": folder_id,
        "status": "OK",
        "issue": "",
        "fix": "",
    }
    try:
        credentials = get_credentials_for_auth_context(
            auth_context,
            scopes=["https://www.googleapis.com/auth/drive.readonly"],
        )
        url = f"https://www.googleapis.com/drive/v3/files/{folder_id}?fields=id,name,owners,permissions&supportsAllDrives=true"
        request = UrlRequest(url, headers={"Authorization": f"Bearer {credentials.token}"})
        with urlopen(request) as response:
            data = json.load(response)
            diagnosis["folder_name"] = data.get("name", "unknown")
    except Exception as exc:
        error_str = str(exc)
        diagnosis["status"] = "ERROR"
        activation_url = ""
        disabled_error = False
        try:
            if hasattr(exc, 'read'):
                payload = json.loads(exc.read().decode('utf-8'))
                activation_url = payload.get('error', {}).get('details', [{}])[-1].get('metadata', {}).get('activationUrl', '')
                errors = payload.get('error', {}).get('errors', [])
                for item in errors:
                    if item.get('reason') in ('accessNotConfigured', 'serviceDisabled'):
                        disabled_error = True
                        break
        except Exception:
            disabled_error = False
        if disabled_error or ("Google Drive API has not been used" in error_str) or ("drive.googleapis.com" in error_str):
            diagnosis["issue"] = "Google Drive API is disabled for this project"
            diagnosis["fix"] = (
                "Enable Google Drive API in the Google Cloud console for this service account project"
                + (f" at {activation_url}" if activation_url else "")
            )
        elif "403" in error_str:
            diagnosis["issue"] = "Access denied (403 Forbidden)"
            if auth_mode == AUTH_MODE_USER_OAUTH:
                diagnosis["fix"] = "The signed-in Google account does not have access to this branch folder."
            else:
                diagnosis["fix"] = (
                    f"Share the Google Drive folder with: {diagnosis['service_account_email']}. "
                    "If this folder is on a Shared Drive, ensure the service account has access there too."
                )
        elif "404" in error_str:
            diagnosis["issue"] = "Folder not found (404)"
            diagnosis["fix"] = "Check that the folder ID is correct"
        elif "API" in error_str or "disabled" in error_str.lower():
            diagnosis["issue"] = "Google Drive API not enabled"
            diagnosis["fix"] = "Enable Google Drive API in GCP project dulcet-velocity-495608-n9"
        else:
            diagnosis["issue"] = error_str
            diagnosis["fix"] = "Check service account permissions and API enablement"
    return diagnosis


def get_target_branch_sheet(branch_index: dict[str, dict[str, Any]], target_branch_id: str) -> dict[str, Any] | None:
    return branch_index.get(target_branch_id)


def find_branch_sheet_for_account(branch_index: dict[str, dict[str, Any]], account_no: str) -> dict[str, Any] | None:
    branch_id = normalize_text(account_no).split("-", 1)[0].upper()
    return branch_index.get(branch_id)
