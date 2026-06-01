# SIMSOFT Project Structure

## Active Runtime

```text
src-tauri/              Tauri Rust desktop shell
src-tauri/src/          Rust commands, validation, Python bridge launcher
src/renderer/           React/TSX desktop UI
src/shared/             TypeScript contracts
core/                   Python business logic
python_backend/         Python workflow orchestration
scripts/python_bridge.py Python command bridge used by Rust
```

## Production Packaging

```text
dist/                   Renderer production build
dist-python/            PyInstaller bundled Python bridge
src-tauri/target/       Rust/Tauri build output
release/                Collected installer and portable artifacts
installer/              Installer-related project assets
assets/                 Icons, images, OCR assets
```

## Runtime Data

```text
config/                 Google OAuth and service account configuration
data/                   duplicate history, locks, cache, access control
logs/                   app logs, audit logs, crash logs
```

For multi-PC deployment, configure shared `data` and `logs` paths through environment variables.

