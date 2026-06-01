# SIMSOFT Troubleshooting

## App Does Not Launch

Check:

- Windows 10/11 WebView2 availability
- antivirus quarantine
- installation folder permissions
- `%LOCALAPPDATA%\SIMSOFT Posting\logs`
- portable `logs/` folder when using the portable package

## Python Bridge Fails

The production app uses the bundled PyInstaller bridge in `dist-python/simsoft-python-bridge/simsoft-python-bridge.exe`.

Run on the build machine:

```powershell
npm run build:bridge
```

Then rebuild the installer:

```powershell
npm run release
```

Set `SIMSOFT_DISABLE_PYTHON_SIDECAR=1` only for emergency diagnosis. Normal production mode should use the long-lived sidecar for performance.

## Google Login Fails

Check:

- `config/oauth_client.json`
- Google Cloud OAuth test user access
- Drive and Sheets API enabled
- operator internet access

## Google Sheet Posting Fails

Check:

- operator has access to the Drive folder and sheet
- branch sheet is selected
- preview is fresh
- posting lock is not held by another PC
- shared storage is configured for multi-PC operation

## OCR Assets Missing

Place production OCR model or image-processing assets in `assets/ocr` before building the release. The folder is bundled automatically.

## Duplicate Protection Does Not Match Across PCs

Configure shared paths:

```text
SIMSOFT_DUPLICATE_HISTORY_PATH=\\SERVER\SIMSOFT\data\duplicate_history.csv
SIMSOFT_POSTED_BATCHES_PATH=\\SERVER\SIMSOFT\data\posted_batches.csv
SIMSOFT_POSTING_LOCKS_PATH=\\SERVER\SIMSOFT\data\posting_locks.json
SIMSOFT_ACCESS_CONTROL_PATH=\\SERVER\SIMSOFT\data\access_control.json
SIMSOFT_LOG_DIR=\\SERVER\SIMSOFT\logs
```
