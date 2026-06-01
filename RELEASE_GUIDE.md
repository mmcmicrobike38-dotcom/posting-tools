# SIMSOFT Release Guide

## Versioning

Update both:

- `package.json`
- `src-tauri/tauri.conf.json`

Keep versions aligned before release.

## Release Flow

```powershell
npm run clean:apply
npm install
npm run doctor
npm run release
```

`npm run release` validates the bundled Python bridge and fails if required release artifacts are missing.

## Release Artifacts

Publish or distribute:

- `release/SIMSOFT_Setup.exe`
- `release/SIMSOFT.msi`

Portable artifacts are useful for admin testing:

- `release/SIMSOFT_Portable.zip`
- `release/SIMSOFT_Portable.exe`
- `release/portable/SIMSOFT Posting/`

## Pilot Checklist

- Install on one clean Windows 10 PC.
- Install on one clean Windows 11 PC.
- Confirm app launch.
- Confirm Google login.
- Confirm Drive folder scan.
- Confirm preview build.
- Confirm dummy branch posting.
- Confirm audit logs.
- Confirm duplicate protection.
- Confirm uninstall.

## Version Update Workflow

1. Update `package.json`.
2. Update `src-tauri/tauri.conf.json`.
3. Run `npm run doctor`.
4. Run `npm run release`.
5. Smoke test installer and portable build.
6. Archive the entire `release/` folder with the version number.

## Updater Preparation

Auto-update is configured with the Tauri v2 updater plugin, GitHub Releases, signed updater artifacts, and the Windows NSIS installer.

## Auto-Update Release Flow

1. Keep these versions aligned:
   - `package.json`
   - `src-tauri/tauri.conf.json`
   - `src-tauri/Cargo.toml`
2. Commit the version change.
3. Tag the release:

```powershell
git tag v1.0.1
git push origin main --tags
```

4. The GitHub Actions workflow `.github/workflows/release.yml` builds the Windows NSIS installer, signs updater artifacts, creates the GitHub Release, uploads the installer, uploads `.sig` files, and uploads `latest.json`.
5. Installed apps check `https://github.com/mmcmicrobike38-dotcom/posting-tools/releases/latest/download/latest.json` on startup.

## Auto-Update Secrets

GitHub Actions requires these repository secrets:

- `TAURI_SIGNING_PRIVATE_KEY`
- `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`

The local signing key files are stored outside the repository:

- `C:\Users\MMC\.tauri\posting-tools\updater.key`
- `C:\Users\MMC\.tauri\posting-tools\updater.key.pub`
- `C:\Users\MMC\.tauri\posting-tools\updater.key.password`

Never commit the private key or password. The public key is embedded in `src-tauri/tauri.conf.json`.

## Auto-Update Release Assets

Each GitHub Release must include:

- Windows NSIS installer `.exe`
- Updater signature `.exe.sig`
- `latest.json`

The Tauri action generates `latest.json` from the signed artifacts when `uploadUpdaterJson` is enabled.

## Local Signed Updater Build

```powershell
npm run release:updater:win
```

To skip rebuilding the Python bridge when `dist-python/` is already current:

```powershell
npm run release:updater:win -- -SkipBridge
```

Generated files are written under `src-tauri/target/release/bundle/nsis/`.

## Private Repository Warning

The current updater endpoint points at this GitHub repository's latest release. If the repository remains private, installed desktop apps cannot download release assets unless the update endpoint is made publicly reachable or replaced with an authenticated/internal update server. For normal customer auto-update behavior, use a public GitHub release repository or host `latest.json` and the installer artifacts on a public HTTPS endpoint.
