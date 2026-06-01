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

The app is versioned and Tauri-bundle ready. A future updater can be added using Tauri's updater plugin and GitHub Releases or an internal release server. Do not enable auto-update until signing, release channels, and rollback procedures are finalized.
