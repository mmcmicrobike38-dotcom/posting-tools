# SIMSOFT Deployment Validation Report

## Current Architecture Status

SIMSOFT Posting is now structured as a Tauri desktop shell with a Rust command layer, React/TypeScript renderer, and a long-lived bundled Python bridge for posting, parsing, and Google Sheets workflows.

## Runtime Flow

1. The Windows user launches the Tauri executable.
2. Tauri loads the compiled renderer from `dist/renderer`.
3. The renderer calls Rust commands through the shared API client.
4. Rust validates IPC input, resolves production-safe paths, and dispatches Python work through the bridge.
5. The Python bridge runs as a long-lived sidecar when available, with a one-shot subprocess fallback.
6. Python services handle Google Drive, Google Sheets, CSV, posting, audit, and workflow logic.
7. Runtime data is stored in `%LOCALAPPDATA%\SIMSOFT Posting\data` for installed mode, or beside the executable in `data` for portable mode.

## Dependency Validation

- UI does not call Python or local files directly; it uses the shared API layer and Tauri commands.
- Rust owns desktop IPC validation, path resolution, subprocess execution, and production logging.
- Python business workflows remain isolated behind a command bridge.
- Google Sheets access is centralized in Python services and credential configuration.
- Release packaging includes the renderer, Rust executable, Python bridge executable, Python workflow modules, config files, assets, and OCR asset folder.

## Production Packaging Validation

The release pipeline performs:

- Node/Vite production renderer build.
- TypeScript tests and backend type checking.
- Python unit tests.
- PyInstaller build for `dist-python/simsoft-python-bridge/simsoft-python-bridge.exe`.
- Tauri release build for MSI and NSIS installers.
- Portable folder and archive creation.
- Artifact checks for `SIMSOFT_Setup.exe`, `SIMSOFT.msi`, and `SIMSOFT_Portable.zip`.

## Clean Windows Compatibility

End-user PCs do not require Node.js, Rust, Cargo, Python, Git, VS Code, or terminal commands. The packaged application includes the compiled Rust desktop binary and the PyInstaller Python bridge.

Google login, Google Drive, and Google Sheets still require internet access and valid credentials. Offline operation is limited to local workflows, cached files, logs, and portable/local data.

## Remaining Release Risks

- The build machine must have the Tauri Windows bundler prerequisites available.
- The current OCR asset folder is packaged, but real OCR model/data files must be placed in `assets/ocr` before OCR features that need external assets are enabled.
- Real Google credential files should be handled as secured deployment assets.
- Final clean-PC validation must be performed on actual Windows 10 and Windows 11 machines after producing signed release artifacts.

