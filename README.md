# SIMSOFT Multi-Tab Posting Automation Tool

Local desktop automation for importing a SIMSOFT Excel export, validating it, previewing ACCOUNTS / RECIEPT / daily report / SCR VS BR updates, generating audit logs, and posting through the Google APIs after the operator completes the guarded Post confirmation.

The tool runs separately from the official Google Sheet. It does not add Apps Script, custom menus, extra tabs, dashboards, images, or structural changes.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

Current Tauri desktop application:

```powershell
npm run dev
```

The root [index.html](index.html) is the Vite renderer entrypoint used by Tauri during development. It is not meant to be opened as a standalone website.

Live posting is controlled in [core/settings.py](core/settings.py):

```python
ENABLE_LIVE_POSTING = False
```

When this flag is `False`, the app shows previews and writes audit previews but does not update Google Sheets. Set it to `True` only after testing with a dummy sheet.

## Authentication Modes

### Service Account

Use this for the original behavior. Put the service account key here:

```text
config/service_account.json
```

The app uses the service account for Drive folder scans, sheet reads, and sheet writes. Google Sheet edit history will show the service account email. Share the Drive folder and branch spreadsheets with that service account.

### User Google Login / OAuth

Use this when Google Sheet edit history must show the human operator. The operator signs in with Google, and all Drive and Sheets API calls use that user's OAuth credentials. In this mode, posting is blocked unless a user is signed in.

Create a Google OAuth Client ID:

1. Open Google Cloud Console for the project that has Google Drive API and Google Sheets API enabled.
2. Go to `APIs & Services` -> `Credentials`.
3. Create `OAuth client ID`.
4. Choose `Desktop app`.
5. Download the JSON file.
6. Save it locally as:

```text
config/oauth_client.json
```

Use [config/oauth_client.example.json](config/oauth_client.example.json) as the shape reference. Do not commit the real OAuth client file.

Required permissions:

- `https://www.googleapis.com/auth/drive.readonly`
- `https://www.googleapis.com/auth/spreadsheets`

The app also requests Google account email identity so it can display and audit the signed-in account. Tokens are stored locally under:

```text
data/oauth_tokens/
```

Use `Logout / Clear Google Login` to clear the active local token. Tokens and credentials are ignored by git.

## Workflow

1. Choose `Service Account` or `User Google Login / OAuth`.
2. Sign in with Google if using User OAuth.
3. Paste the Google Drive branch folder link.
4. Scan the folder.
5. Select the target branch.
6. Upload the SIMSOFT Excel export.
7. Review ACCOUNTS, RECIEPT, daily report, and SCR VS BR previews.
8. Resolve validation errors and duplicates.
9. Click the guarded `Post` control.
10. Review the final confirmation dialog and choose `Continue Posting`. The selected authentication mode is used for the actual Google Sheets write requests.

## Desktop Application

The desktop UI lives in [src/renderer](src/renderer). It is a Tauri + React application that reuses the Python posting engine through [scripts/python_bridge.py](scripts/python_bridge.py).

Desktop layout:

- Left sidebar: operator/auth status, SIMSOFT file picker, Google Drive folder link, `SCAN FOLDER`, target branch dropdown, test mode.
- Main dashboard: posting review, next-step guidance, preview tables for ACCOUNTS, daily tab, RECIEPT, and SCR VS BR.
- Bottom/sidebar area: operator guidance, auth/sheet/SIMSOFT/posting/cache status cards, and a guarded `Post` control.

The desktop app keeps the same posting lock rules:

- Authentication must be connected.
- Google folder scan and target branch selection must be ready.
- Sheet tabs must load successfully.
- SIMSOFT validation and previews must have no blocking errors.
- The preview state must be fresh.
- The branch must not be locked by another posting operator.
- The operator must use the guarded Post control and accept the final confirmation dialog.

Long-running tasks such as Google login, Drive scanning, preview building, and posting run through background workers so the UI stays responsive.

## Packaging

The project packages with Tauri. Run the full verification command before creating an installer:

```powershell
npm run verify
```

Build the Windows desktop installer:

```powershell
npm run package
```

This command verifies the app, builds the bundled Python bridge executable, and packages the Tauri installer. Target PCs do not need a separate Python installation.

Credentials are deployment files, not source files. Place the intended production files on each workstation or set the matching `.env` paths:

- `config/service_account.json`
- `config/oauth_client.json`

Keep real credential files restricted to trusted team machines.

User OAuth tokens are intentionally not bundled:

- `data/oauth_tokens/`

Place user token files beside the packaged app only when a deployment plan explicitly requires pre-provisioned OAuth tokens.

Use [docs/ROLLOUT.md](docs/ROLLOUT.md) for workstation testing, shared-storage setup, operator onboarding, live-posting pilot checks, and support collection.

Pre-release checklist:

- Confirm `npm run verify` passes.
- Confirm `config/oauth_client.json` and `config/service_account.json` are the intended team credentials before packaging.
- Run a login, folder scan, sheet update, SIMSOFT validation, and preview on a dummy branch.
- Enable `ENABLE_LIVE_POSTING` only for the release build intended to write to production sheets.
- Package with `npm run package:win` and install on one test workstation before distributing.

Basic update flow:

1. Increase `version` in [package.json](package.json).
2. Run `npm run verify`.
3. Build with `npm run package:win`.
4. Install on one pilot workstation.
5. Confirm health check, login, scan, update sheet, validation, and a dummy preview.
6. Distribute the installer only after the pilot workstation passes.

## Posting Gate

Posting stays locked unless:

- Authentication is ready.
- User OAuth mode has a signed-in Google user.
- The branch folder scan is complete.
- A target branch is selected.
- The target branch sheet is accessible.
- The SIMSOFT file is parsed.
- Validation has no blocking errors.
- The validated preview state is fresh.
- Duplicate checks pass.
- No unresolved IBP, Other Payment, or SCR VS BR issues remain.
- No active branch posting lock exists for the target branch.
- Live posting is enabled.

When posting is locked, the UI shows the first actionable reason, such as `Validation errors must be fixed.`, `Select target branch first.`, `Folder scan required.`, `Preview is stale. Please revalidate.`, `Branch is locked by another operator.`, `Unresolved IBP lookup issue.`, or `Google authentication required.`

## Smart Cache Strategy

The app caches only metadata and session-derived work that is safe to reuse:

- Branch folder scan results: branch IDs, branch names, spreadsheet IDs, filenames, and folder metadata.
- Parsed SIMSOFT transactions for the currently selected file.
- Preview data generated from the validated SIMSOFT file and fresh sheet reads.
- Session-level IBP lookup results so repeated IBP accounts do not reread the same source branch sheet.
- Duplicate history loaded into memory for fast local duplicate checks.

The app does not permanently cache live Google Sheet contents. These are refreshed for validation and checked again before final posting:

- ACCOUNTS, RECIEPT, SCR VS BR, and daily tab rows.
- Sheet headers and posting ranges.
- Branch lock state.
- Duplicate history when a shared store is used.

Cache status indicators:

- `Branch Folder Cache`: `Fresh`, `Not Scanned`, or `Stale`.
- `SIMSOFT Parse Cache`: `Ready` or `Needs Upload`.
- `Preview State`: `Fresh` or `Stale`.
- `Target Sheet Data`: `Freshly Validated` or `Needs Revalidation`.

Use `Refresh Folder Scan` after branch files are added, removed, or renamed in Drive. Use `Refresh Google Sheet Data` to revalidate live sheet data and rebuild previews. If the app shows `Preview is stale. Please revalidate.`, refresh/revalidate before posting; the previous preview is no longer accepted as the source of truth.

### Fast Branch Folder Scan

`Scan Branch Folder` is metadata-only. It uses Google Drive `files.list` with a narrow field mask for file ID, name, MIME type, modified time, web view link, and shortcut target details. It does not open the 80+ branch spreadsheets and does not read ACCOUNTS, RECIEPT, SCR VS BR, or daily tab contents.

The branch dropdown is built from file names by detecting `MMC` followed by three digits, for example `MMC038 - POZORRUBIO REALTIME 2026`. Google Drive shortcuts are resolved when their target is a Google Sheet. If multiple files contain the same branch ID, the branch is marked `MULTIPLE_MATCHES`, all matching file names are retained, and posting is blocked for that branch until the duplicate is fixed.

Actual worksheet contents are loaded lazily:

- The selected target branch sheet is read during validation/posting only.
- Only required target tabs are loaded: ACCOUNTS, RECIEPT, SCR VS BR, and the detected daily tab.
- IBP source branch ACCOUNTS data is loaded only when an IBP transaction references that source branch.

Timing logs include `drive_folder_scan_duration`, `branch_index_build_duration`, `target_sheet_load_duration`, and `ibp_source_sheet_load_duration`.

## Multi-User Readiness

The desktop app is designed for a safe baseline of 5-10 simultaneous operators and an optimized target of 10-20 operators when Drive scans, sheet reads, preview generation, and posting are cached and batched. If more than 20 users are expected, move to a centralized server/queue/database architecture so all posting is serialized through one shared service.

Concurrency protections:

- Branch-level posting locks prevent two operators from posting to the same target branch at the same time.
- Locks include branch ID, spreadsheet ID, batch ID, operator email, and lock timestamps, and expire automatically if a posting attempt becomes stale.
- Each validation/posting run receives a unique batch ID.
- Posting checks idempotency by batch ID and transaction key before writing.
- Before posting, the app checks whether the target sheet changed after validation and asks the operator to revalidate if it did.
- Google writes are batched by tab, and temporary Google quota/rate-limit errors are retried with exponential backoff and jitter.
- Google Drive branch scans are cached for the session and persisted for 12 hours in `data/cache/branch_index.json`; use `Refresh Folder Scan` only when branch files were added, renamed, or removed.

Authentication behavior:

- Service Account mode is easier to manage, but all edits appear under the service account and all users share that account's Google API quota.
- User OAuth mode shows the actual user in Google Sheet history, but every operator must have access to the Drive folder and target branch sheets.

Duplicate/audit storage:

- The current local duplicate history protects only one PC.
- For multiple PCs, configure shared duplicate/audit/lock/access paths in `.env` using `SIMSOFT_DUPLICATE_HISTORY_PATH`, `SIMSOFT_POSTED_BATCHES_PATH`, `SIMSOFT_POSTING_LOCKS_PATH`, `SIMSOFT_ACCESS_CONTROL_PATH`, and `SIMSOFT_LOG_DIR`.
- The app now has cloud-ready store interfaces under [core/stores](core/stores): `DuplicateStore`, `AuditStore`, `BranchLockStore`, `BranchIndexStore`, and `IBPLookupCacheStore`.
- Local mode uses CSV/JSON/session-memory implementations. Future production mode can replace these with Supabase, Firebase, PostgreSQL, or a Cloud Run backend without changing posting business rules.

Known limitations:

- Local duplicate and lock files protect one shared workstation best. For multiple PCs, use a shared database or backend store.
- Branch folder metadata may be up to the cache TTL old unless `Refresh Folder Scan` is clicked.
- Live sheet contents are intentionally not trusted from cache; validation/posting may take longer because fresh reads are required for safety.

## Audit and Duplicate Files

- `logs/audit_<batch-id>.csv`
- `data/duplicate_history.csv`
- `data/posted_batches.csv`
- `data/posting_locks.json`

Audit rows include auth metadata such as `batch_id`, `auth_mode`, `google_actor_email`, `operator_email`, `operator_name`, `target_branch_id`, `target_branch_name`, `target_spreadsheet_id`, `branch_lock_id`, `validation_snapshot_id`, `preview_generated_at`, `posted_at`, lock timestamps, and `confirmation_method`. Access tokens and refresh tokens are never written to logs.

For guarded Post audit trails, `confirmation_method` remains:

```text
swipe_to_post
```

Duplicate key:

`Account Name + Date + Reference + Amount + Rebate + Interest`

## Troubleshooting

- Service account mode shows the service account in edit history: this is expected.
- User OAuth mode shows the signed-in user in edit history only when the signed-in user has edit access and posting is done in User OAuth mode.
- Folder scan error in User OAuth mode usually means the signed-in Google account does not have access to the Drive folder.
- Sheet connection error usually means the signed-in user or service account lacks access to the branch spreadsheet, or a required tab name is missing.
- If OAuth login cannot start, confirm `config/oauth_client.json` exists and is a Desktop App OAuth Client ID JSON.
- If Drive or Sheets API errors mention disabled APIs, enable Google Drive API and Google Sheets API in the Google Cloud project.

## Project Structure

- [src/renderer](src/renderer) - React desktop UI.
- [src-tauri](src-tauri) - Tauri desktop shell and native packaging.
- [src/backend](src/backend) - backend services, validation, caching, scanning, and Python bridge caller.
- [scripts/python_bridge.py](scripts/python_bridge.py) - bridge from the desktop app to the Python posting engine.
- [python_backend/services/workflow_service.py](python_backend/services/workflow_service.py) - Python workflow service used by the bridge.
- [python_backend/models/app_state.py](python_backend/models/app_state.py) - Python workflow state model used by the bridge.
- [core/google_sheets.py](core/google_sheets.py) - Google auth, Drive/Sheets clients, worksheet helpers.
- [core/branch_folder_lookup.py](core/branch_folder_lookup.py) - Drive folder scan and branch sheet detection.
- [core/parser.py](core/parser.py) - SIMSOFT parsing, dates, amounts, accounts, references, duplicate keys.
- [core/accounts.py](core/accounts.py) - ACCOUNTS preview and update preparation.
- [core/daily_report.py](core/daily_report.py) - daily tab detection and row preview.
- [core/receipt.py](core/receipt.py) - RECIEPT series lookup and preview.
- [core/scr_vs_br.py](core/scr_vs_br.py) - SCR VS BR receipt block continuation logic.
- [core/audit.py](core/audit.py) - audit CSV and duplicate history.
- [core/stores](core/stores) - cloud-ready store interfaces and local implementations.
- [tests/test_core.py](tests/test_core.py) - unit tests for Python core rules.
- [tests-ts](tests-ts) - unit tests for TypeScript backend rules.

## Tests

```powershell
.\.venv\Scripts\python -m pytest tests -q
```
