# SIMSOFT Posting Rollout Runbook

Use this runbook before giving the app to operators. The goal is to prove the workstation, Google access, shared storage, and operator workflow before live posting.

## 1. Workstation Smoke Test

Run on every target PC:

1. Install the packaged app.
2. Place `config/oauth_client.json` and/or `config/service_account.json` in the configured deployment location.
3. Open the app and sign in with Google.
4. Open `Advanced Settings`.
5. Click `Run Health Check`.
6. Confirm Python bridge, OAuth client, data folder, log folder, duplicate history, and posting locks are ready.
7. Click `Open Logs` and confirm the support folder opens.

Pass condition: health check is green or every warning has a known reason.

## 2. Multi-PC Storage Setup

For one shared workstation, local `data/` is acceptable.

For two or more posting PCs, configure these `.env` values to a shared network folder that every posting PC can read and write:

```text
SIMSOFT_DUPLICATE_HISTORY_PATH=\\SERVER\SIMSOFT\data\duplicate_history.csv
SIMSOFT_POSTED_BATCHES_PATH=\\SERVER\SIMSOFT\data\posted_batches.csv
SIMSOFT_POSTING_LOCKS_PATH=\\SERVER\SIMSOFT\data\posting_locks.json
SIMSOFT_ACCESS_CONTROL_PATH=\\SERVER\SIMSOFT\data\access_control.json
SIMSOFT_LOG_DIR=\\SERVER\SIMSOFT\logs
```

Pass condition: `Advanced Settings` shows shared storage configured, and two PCs can both run health check successfully.

Important: Google OAuth test users do not automatically appear in the SIMSOFT Access List. The Access List is the SIMSOFT permission file. To manage the same admins, members, and branch assignments across PCs, all PCs must use the same `SIMSOFT_ACCESS_CONTROL_PATH`.

## 3. Non-Technical Operator Test

Ask one real operator to complete this without developer help:

1. Sign in with Google.
2. Paste the Drive folder link.
3. Scan the folder.
4. Select a target branch.
5. Update the selected sheet.
6. Choose a SIMSOFT file.
7. Validate the file.
8. Read the next-step message.
9. Explain whether the app is ready to post or what must be fixed.

Record any confusing labels, button colors, or messages. Fix wording before adding more users.

Pass condition: the operator can complete preview validation and explain the blocker/ready state.

## 4. Live Posting Pilot

Use one dummy branch first.

1. Confirm `npm run verify` passes before packaging.
2. Confirm `ENABLE_LIVE_POSTING = True` only for the intended release.
3. Post one small SIMSOFT batch.
4. Confirm Google Sheet rows changed correctly.
5. Confirm audit CSV was created.
6. Confirm duplicate history contains the posted transaction keys.
7. Try the same batch again and confirm it is blocked as duplicate.

Pass condition: posting is correct, audited, and duplicate-protected.

## 5. Support Checklist

When an operator reports a problem, collect:

- Screenshot of the dashboard.
- Current next-step message.
- Health check result.
- Latest files from `Open Logs`.
- The audit CSV for the affected batch, if posting reached preview or post.
- Whether the PC is using local or shared storage.

Do not collect OAuth tokens, service account keys, or real Google credential files.
