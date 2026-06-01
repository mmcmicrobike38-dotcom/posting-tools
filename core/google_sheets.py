from __future__ import annotations

import base64
import ctypes
import json
import os
import random
import re
import sys
import time
import wsgiref.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen

from google.auth.transport.requests import Request as AuthRequest
from google.oauth2.credentials import Credentials as UserCredentials
from google.oauth2.service_account import Credentials

AUTH_MODE_SERVICE_ACCOUNT = "Service Account"
AUTH_MODE_USER_OAUTH = "User Google Login / OAuth"
DEFAULT_SERVICE_ACCOUNT_PATH = Path(os.getenv("SIMSOFT_SERVICE_ACCOUNT_JSON_PATH", "config/service_account.json"))
DEFAULT_OAUTH_CLIENT_PATH = Path(os.getenv("SIMSOFT_OAUTH_CLIENT_JSON_PATH", "config/oauth_client.json"))
DEFAULT_OAUTH_TOKEN_DIR = Path(os.getenv("SIMSOFT_OAUTH_TOKEN_DIR", "data/oauth_tokens"))
GOOGLE_API_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
]
USER_IDENTITY_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]
USER_OAUTH_SCOPES = GOOGLE_API_SCOPES + USER_IDENTITY_SCOPES
TOKEN_ENCRYPTION_VERSION = "simsoft-dpapi-v1"
OAUTH_SUCCESS_HTML = """<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <title>SIMSOFT Login Complete</title>
    <style>
      body {
        margin: 0;
        display: grid;
        min-height: 100vh;
        place-items: center;
        background: #f8fafc;
        color: #172033;
        font: 14px "Segoe UI", Arial, sans-serif;
      }
      main {
        width: min(360px, calc(100vw - 32px));
        padding: 24px;
        border: 1px solid #d9e0ea;
        border-radius: 8px;
        background: #ffffff;
        box-shadow: 0 16px 40px rgba(23, 32, 51, 0.12);
        text-align: center;
      }
      h1 {
        margin: 0 0 8px;
        font-size: 20px;
      }
      p {
        margin: 0;
        color: #667085;
        line-height: 1.45;
      }
    </style>
  </head>
  <body>
    <main>
      <h1>Login complete</h1>
      <p>Returning to SIMSOFT...</p>
    </main>
    <script>
      setTimeout(() => {
        window.open("", "_self");
        window.close();
      }, 350);
    </script>
  </body>
</html>"""


class AutoCloseOAuthSuccessApp:
    def __init__(self, success_message: str):
        self.last_request_uri = None
        self._success_message = success_message

    def __call__(self, environ: dict[str, Any], start_response: Any) -> list[bytes]:
        start_response("200 OK", [("Content-type", "text/html; charset=utf-8")])
        self.last_request_uri = wsgiref.util.request_uri(environ)
        return [self._success_message.encode("utf-8")]


@dataclass
class GoogleClients:
    drive_service: Any
    sheets_service: Any
    credentials: Any
    current_user_email: str
    auth_mode: str


def extract_spreadsheet_id(sheet_url: str) -> str:
    patterns = [r"/spreadsheets/d/([a-zA-Z0-9-_]+)", r"[?&]id=([a-zA-Z0-9-_]+)"]
    for pattern in patterns:
        match = re.search(pattern, sheet_url or "")
        if match:
            return match.group(1)
    if re.fullmatch(r"[a-zA-Z0-9-_]{20,}", sheet_url or ""):
        return sheet_url
    raise ValueError("Could not extract a Google spreadsheet ID from the URL.")


def load_service_account_json(uploaded_file: Any) -> dict[str, Any]:
    if uploaded_file is None:
        raise ValueError("Service Account JSON is required.")
    raw = uploaded_file.getvalue() if hasattr(uploaded_file, "getvalue") else uploaded_file.read()
    info = json.loads(raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw.lstrip("\ufeff"))
    validate_service_account_info(info)
    return info


def validate_service_account_info(info: dict[str, Any]) -> None:
    required = ["type", "project_id", "private_key", "client_email", "token_uri"]
    missing = [field for field in required if not info.get(field)]
    if missing:
        raise ValueError(f"Service Account JSON is missing required fields: {', '.join(missing)}")
    if info.get("type") != "service_account":
        raise ValueError("Uploaded JSON must be a Google service account key with type=service_account.")
    client_id = str(info.get("client_id", "")).strip()
    if client_id and not client_id.isdigit():
        raise ValueError(
            "Service Account JSON has an invalid client_id. Do not paste the Google Sheet URL inside the JSON file. "
            "Paste the Google Sheet URL in the app's Google Sheet link field instead."
        )


def load_oauth_client_json(path: str | Path = DEFAULT_OAUTH_CLIENT_PATH) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def validate_oauth_client_info(info: dict[str, Any]) -> None:
    installed = info.get("installed")
    if not isinstance(installed, dict):
        raise ValueError("OAuth Client JSON must be a Google Desktop app client with an 'installed' section.")
    required = ["client_id", "project_id", "auth_uri", "token_uri", "client_secret"]
    missing = [field for field in required if not installed.get(field)]
    if missing:
        raise ValueError(f"OAuth Client JSON is missing required fields: {', '.join(missing)}")
    placeholders = [field for field in ["client_id", "project_id", "client_secret"] if "REPLACE_WITH" in str(installed.get(field, ""))]
    if placeholders:
        raise ValueError(
            "OAuth Client JSON still contains placeholder values. Download a real Desktop app OAuth Client ID JSON "
            "from Google Cloud Console and replace config/oauth_client.json."
        )
    if not str(installed.get("client_id", "")).endswith(".apps.googleusercontent.com"):
        raise ValueError("OAuth Client JSON client_id does not look like a Google OAuth Client ID.")


def validate_oauth_client_json_path(path: str | Path = DEFAULT_OAUTH_CLIENT_PATH) -> None:
    validate_oauth_client_info(load_oauth_client_json(path))


def get_service_account_credentials(service_account_info: dict[str, Any], scopes: list[str] | None = None):
    effective_scopes = scopes or ["https://www.googleapis.com/auth/spreadsheets"]
    return Credentials.from_service_account_info(service_account_info, scopes=effective_scopes)


def load_service_account_json_path(path: str | Path = DEFAULT_SERVICE_ACCOUNT_PATH) -> dict[str, Any]:
    with Path(path).open("rb") as fh:
        return load_service_account_json(fh)


def _sanitize_token_user(email: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.@-]+", "_", email.strip().lower()) or "user"


def active_oauth_user_path(token_dir: str | Path = DEFAULT_OAUTH_TOKEN_DIR) -> Path:
    return Path(token_dir) / "active_user.txt"


def oauth_token_path_for_email(email: str, token_dir: str | Path = DEFAULT_OAUTH_TOKEN_DIR) -> Path:
    return Path(token_dir) / f"{_sanitize_token_user(email)}.json"


def _dpapi_available() -> bool:
    return sys.platform == "win32"


def _dpapi_cryptprotect(data: bytes) -> bytes:
    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    input_buffer = ctypes.create_string_buffer(data)
    input_blob = DataBlob(len(data), ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_char)))
    output_blob = DataBlob()
    if not crypt32.CryptProtectData(ctypes.byref(input_blob), "SIMSOFT OAuth token", None, None, None, 0, ctypes.byref(output_blob)):
        raise OSError("Windows DPAPI token encryption failed.")
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


def _dpapi_cryptunprotect(data: bytes) -> bytes:
    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    input_buffer = ctypes.create_string_buffer(data)
    input_blob = DataBlob(len(data), ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_char)))
    output_blob = DataBlob()
    if not crypt32.CryptUnprotectData(ctypes.byref(input_blob), None, None, None, None, 0, ctypes.byref(output_blob)):
        raise OSError("Windows DPAPI token decryption failed.")
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


def protect_oauth_token_json(raw_json: str) -> str:
    if not _dpapi_available():
        return raw_json
    encrypted = _dpapi_cryptprotect(raw_json.encode("utf-8"))
    return json.dumps(
        {
            "simsoft_encrypted": True,
            "version": TOKEN_ENCRYPTION_VERSION,
            "provider": "windows-dpapi-current-user",
            "ciphertext": base64.b64encode(encrypted).decode("ascii"),
        },
        indent=2,
    )


def unprotect_oauth_token_json(stored_json: str) -> str:
    data = json.loads(stored_json)
    if not isinstance(data, dict) or not data.get("simsoft_encrypted"):
        return stored_json
    if data.get("version") != TOKEN_ENCRYPTION_VERSION:
        raise ValueError("Unsupported encrypted OAuth token format.")
    ciphertext = str(data.get("ciphertext") or "")
    if not ciphertext:
        raise ValueError("Encrypted OAuth token is missing ciphertext.")
    return _dpapi_cryptunprotect(base64.b64decode(ciphertext)).decode("utf-8")


def read_oauth_token_info(token_path: Path) -> dict[str, Any]:
    raw = token_path.read_text(encoding="utf-8")
    return json.loads(unprotect_oauth_token_json(raw))


def oauth_token_file_is_encrypted(token_path: Path) -> bool:
    try:
        data = json.loads(token_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return isinstance(data, dict) and data.get("simsoft_encrypted") is True


def get_oauth_user_info(credentials: Any) -> dict[str, str]:
    from google.auth.transport.requests import AuthorizedSession

    authed_session = AuthorizedSession(credentials)
    response = authed_session.get("https://www.googleapis.com/oauth2/v2/userinfo")
    response.raise_for_status()
    data = response.json()
    return {
        "email": data.get("email", ""),
        "name": data.get("name", ""),
    }


def get_oauth_user_email(credentials: Any) -> str:
    return get_oauth_user_info(credentials).get("email", "")


def save_user_oauth_credentials(credentials: Any, email: str, token_dir: str | Path = DEFAULT_OAUTH_TOKEN_DIR) -> Path:
    token_root = Path(token_dir)
    token_root.mkdir(parents=True, exist_ok=True)
    token_path = oauth_token_path_for_email(email, token_root)
    token_path.write_text(protect_oauth_token_json(credentials.to_json()), encoding="utf-8")
    try:
        os.chmod(token_path, 0o600)
    except OSError:
        pass
    active_oauth_user_path(token_root).write_text(email, encoding="utf-8")
    return token_path


def clear_user_oauth_credentials(email: str | None = None, token_dir: str | Path = DEFAULT_OAUTH_TOKEN_DIR) -> None:
    token_root = Path(token_dir)
    if email:
        token_path = oauth_token_path_for_email(email, token_root)
        if token_path.exists():
            token_path.unlink()
    active_path = active_oauth_user_path(token_root)
    if active_path.exists():
        active_path.unlink()


def load_user_oauth_credentials(token_dir: str | Path = DEFAULT_OAUTH_TOKEN_DIR) -> tuple[Any | None, str]:
    token_root = Path(token_dir)
    active_path = active_oauth_user_path(token_root)
    if not active_path.exists():
        return None, ""
    email = active_path.read_text(encoding="utf-8").strip()
    if not email:
        return None, ""
    token_path = oauth_token_path_for_email(email, token_root)
    if not token_path.exists():
        return None, email
    try:
        token_info = read_oauth_token_info(token_path)
    except Exception:
        clear_user_oauth_credentials(email, token_root)
        return None, email
    if _dpapi_available() and not oauth_token_file_is_encrypted(token_path):
        token_path.write_text(protect_oauth_token_json(json.dumps(token_info)), encoding="utf-8")
    credentials = UserCredentials.from_authorized_user_info(token_info, USER_OAUTH_SCOPES)
    if credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(AuthRequest())
            save_user_oauth_credentials(credentials, email, token_root)
        except Exception:
            clear_user_oauth_credentials(email, token_root)
            return None, email
    if not credentials.valid:
        return None, email
    return credentials, email


def run_user_oauth_login(
    oauth_client_path: str | Path = DEFAULT_OAUTH_CLIENT_PATH,
    token_dir: str | Path = DEFAULT_OAUTH_TOKEN_DIR,
) -> tuple[Any, str]:
    from google_auth_oauthlib import flow as oauth_flow

    client_path = Path(oauth_client_path)
    if not client_path.exists():
        raise FileNotFoundError(f"OAuth Client ID JSON not found at {client_path}")
    oauth_flow._RedirectWSGIApp = AutoCloseOAuthSuccessApp
    flow = oauth_flow.InstalledAppFlow.from_client_secrets_file(str(client_path), scopes=USER_OAUTH_SCOPES)
    credentials = flow.run_local_server(port=0, success_message=OAUTH_SUCCESS_HTML)
    email = get_oauth_user_email(credentials)
    if not email:
        raise ValueError("Google login succeeded, but the account email could not be read.")
    save_user_oauth_credentials(credentials, email, token_dir)
    return credentials, email


def get_credentials_for_auth_context(auth_context: Any, scopes: list[str] | None = None):
    if isinstance(auth_context, dict) and auth_context.get("credentials") is not None:
        credentials = auth_context["credentials"]
        if not credentials.valid:
            credentials.refresh(AuthRequest())
        return credentials
    return get_service_account_credentials(auth_context, scopes=scopes)


def create_google_clients(
    auth_mode: str,
    service_account_path: str | Path | None = None,
    oauth_client_path: str | Path | None = None,
    token_path: str | Path | None = None,
    service_account_info: dict[str, Any] | None = None,
    credentials: Any | None = None,
) -> GoogleClients:
    from googleapiclient.discovery import build

    if auth_mode == AUTH_MODE_SERVICE_ACCOUNT:
        info = service_account_info or load_service_account_json_path(service_account_path or DEFAULT_SERVICE_ACCOUNT_PATH)
        creds = credentials or get_service_account_credentials(info, scopes=GOOGLE_API_SCOPES)
        email = info.get("client_email", "")
    elif auth_mode == AUTH_MODE_USER_OAUTH:
        token_dir = token_path or DEFAULT_OAUTH_TOKEN_DIR
        if credentials is None:
            creds, email = load_user_oauth_credentials(token_dir)
        else:
            creds = credentials
            email = get_oauth_user_email(creds)
        if creds is None:
            raise PermissionError("User OAuth mode requires a signed-in Google user.")
    else:
        raise ValueError(f"Unknown authentication mode: {auth_mode}")
    if not creds.valid:
        creds.refresh(AuthRequest())
    return GoogleClients(
        drive_service=build("drive", "v3", credentials=creds),
        sheets_service=build("sheets", "v4", credentials=creds),
        credentials=creds,
        current_user_email=email,
        auth_mode=auth_mode,
    )


def google_actor_email(auth_context: Any) -> str:
    if isinstance(auth_context, dict):
        return auth_context.get("current_user_email") or auth_context.get("client_email", "")
    return ""


def list_drive_spreadsheets_in_folder(auth_context: Any, folder_id: str) -> list[dict[str, Any]]:
    credentials = get_credentials_for_auth_context(
        auth_context,
        scopes=["https://www.googleapis.com/auth/drive.readonly", "https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    if not credentials.valid:
        credentials.refresh(AuthRequest())
    query = f"'{folder_id}' in parents and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
    params = {
        "q": query,
        "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,webViewLink)",
        "pageSize": "1000",
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
    }
    url = f"https://www.googleapis.com/drive/v3/files?{urlencode(params, safe="'()")}"  # preserve quotes and parentheses
    request = UrlRequest(url, headers={"Authorization": f"Bearer {credentials.token}"})
    with urlopen(request) as response:
        data = json.load(response)
    return data.get("files", [])


def get_gspread_client(auth_context: Any):
    import gspread

    credentials = get_credentials_for_auth_context(auth_context, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(credentials)


def fetch_worksheet_rows(sheet_url: str, worksheet_name: str, auth_context: Any):
    spreadsheet_id = extract_spreadsheet_id(sheet_url)
    client = get_gspread_client(auth_context)
    spreadsheet = client.open_by_key(spreadsheet_id)
    worksheet = spreadsheet.worksheet(worksheet_name)
    return worksheet, worksheet.get_all_values()


def row_headers(rows: list[list[Any]], header_row_number: int) -> list[str]:
    if header_row_number < 1:
        raise ValueError("Header row number must be 1 or greater.")
    if len(rows) < header_row_number:
        raise ValueError("Target worksheet does not contain the configured header row.")
    return rows[header_row_number - 1]


def column_number_to_letter(column_number: int) -> str:
    result = ""
    while column_number:
        column_number, remainder = divmod(column_number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def grouped_a1_updates(updates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"range": f"{column_number_to_letter(update['col'])}{update['row']}", "values": [[update["value"]]]}
        for update in updates
    ]


def is_transient_google_error(exc: Exception) -> bool:
    message = str(exc)
    markers = [
        "429",
        "500",
        "502",
        "503",
        "504",
        "Quota exceeded",
        "Rate Limit",
        "rateLimitExceeded",
        "userRateLimitExceeded",
        "Too Many Requests",
    ]
    return any(marker in message for marker in markers)


def retry_google_operation(operation: Any, *, attempts: int = 5, base_delay: float = 1.0) -> Any:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            if not is_transient_google_error(exc) or attempt == attempts - 1:
                raise
            delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
            time.sleep(delay)
    assert last_error is not None
    raise last_error


def post_to_google_sheet(worksheet: Any, updates: list[dict[str, Any]]) -> None:
    if updates:
        raw_updates = [update for update in updates if update.get("value_input_option") == "RAW"]
        user_entered_updates = [update for update in updates if update.get("value_input_option") != "RAW"]
        if raw_updates:
            raw_payload = grouped_a1_updates(raw_updates)
            retry_google_operation(lambda: worksheet.batch_update(raw_payload, value_input_option="RAW"))
        if user_entered_updates:
            user_entered_payload = grouped_a1_updates(user_entered_updates)
            retry_google_operation(lambda: worksheet.batch_update(user_entered_payload, value_input_option="USER_ENTERED"))
