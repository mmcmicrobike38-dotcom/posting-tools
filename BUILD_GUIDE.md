# SIMSOFT Build Guide

This project builds a self-contained Tauri Windows desktop app. End-user PCs do not need Node.js, Rust, Cargo, Python, Git, VS Code, or terminal commands.

## Build Machine Requirements

- Windows 10 or Windows 11
- Node.js and npm
- Rust toolchain with Cargo
- Python virtual environment at `.venv`
- Python dependencies installed from `requirements.txt`
- Tauri prerequisites for Windows packaging

These requirements apply only to the build machine, not member/operator PCs.

## Commands

```powershell
npm run dev
npm run tauri:dev
npm run doctor
npm run build
npm run verify
npm run build:bridge
npm run tauri:build
npm run installer
npm run portable
npm run release
npm run clean
```

`npm run release` performs:

- environment checks
- TypeScript/React build
- TypeScript tests
- backend typecheck
- Python tests
- PyInstaller Python bridge build
- Tauri MSI/NSIS build
- portable package generation
- artifact collection into `release/`

## Outputs

After a successful release build:

```text
release/SIMSOFT_Setup.exe
release/SIMSOFT.msi
release/SIMSOFT_Portable.exe
release/SIMSOFT_Portable.zip
release/portable/SIMSOFT Posting/
```

The installer is the recommended deployment artifact.

## Bundled Runtime

The release includes:

- compiled Tauri/Rust application binary
- compiled React renderer
- PyInstaller Python bridge at `dist-python/simsoft-python-bridge/simsoft-python-bridge.exe`
- Python workflow modules from `core/` and `python_backend/`
- Google credential deployment files from `config/`
- OCR/image assets from `assets/ocr`
- production scripts and release metadata

Installed mode stores mutable data under `%LOCALAPPDATA%\SIMSOFT Posting`. Portable mode stores mutable data beside the executable in `data/`, `logs/`, and `storage/`.
