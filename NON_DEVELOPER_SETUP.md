# Non-Developer PC Setup

This is the operator/member setup.

## Requirements

- Windows 10 or Windows 11
- Internet access for Google login and Google Sheets features
- Access to the company Google Drive branch folder

The operator PC does not need:

- Node.js
- Rust
- Cargo
- Python
- Git
- VS Code
- terminal commands

## Install

1. Run `SIMSOFT_Setup.exe`.
2. Open SIMSOFT Posting.
3. Sign in with Google.
4. Request access if the app asks.
5. Wait for admin approval.
6. Start daily posting workflow.

## Portable Admin Test

Admins may use `SIMSOFT_Portable.zip` to test without installation. Extract the full folder before running the executable so bundled resources stay beside the app.

## Offline Behavior

The app can open and manage local runtime files offline. Google login, Google Drive scanning, and Google Sheets posting require internet access.

## What Is Included

The installer and portable package include the desktop executable, compiled frontend, bundled Python bridge, Python workflow code, OCR asset folder, and deployment config files. Operators should not install Python or run setup commands.
