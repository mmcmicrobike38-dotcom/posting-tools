# SIMSoft Posting Clean Modular Architecture

## Goals

SIMSoft Posting is a local-first desktop system. The architecture must keep the current posting flow stable while making the codebase easier to scale into background workers, PostgreSQL, OCR, synchronization, and future API/mobile clients.

The dependency rule is strict:

```text
presentation -> application -> domain
presentation -> infrastructure only through application ports/adapters
infrastructure -> application/domain contracts
domain -> no framework, database, Tauri, React, Google, filesystem, or Python bridge dependencies
```

## Current Runtime Map

```text
src/renderer/                       React desktop UI
src/renderer/tauriBridge.ts          Tauri IPC adapter exposed as window.simsoft
src-tauri/src/lib.rs                 Tauri commands, validation, file paths, Python bridge process runner
scripts/python_bridge.py             JSON command bridge from Rust to Python
python_backend/services/             workflow orchestration
core/                                posting, parsing, Google Sheets, audit, duplicate rules
data/                                local cache, access control, duplicate/posting history
config/                              Google OAuth/service-account files
logs/                                runtime and audit logs
```

## Target Repository Structure

```text
apps/
  desktop/
    README.md
    src/
      main.tsx
      app/
        AppShell.tsx
        routes.tsx
        providers.tsx
      bridge/
        simsoftDesktopApi.ts
        tauriInvokeClient.ts

backend/
  api/
    README.md
    commands/
      posting_commands.rs
      auth_commands.rs
      admin_commands.rs
      system_commands.rs
    middleware/
      error_mapping.rs
      auth_guard.rs
    dto/
      posting_dto.rs
      auth_dto.rs
      system_dto.rs
  application/
    README.md
    common/
      unit_of_work.rs
      command_bus.rs
      event_bus.rs
      validation.rs
    modules/
      posting/
        commands/
        events/
        handlers/
        services/
        ports/
        dto/
      authentication/
      user_management/
      branch_management/
      audit_logs/
      dashboard/
      reports/
      ocr/
      notifications/
      synchronization/
  domain/
    README.md
    common/
      entity.rs
      value_object.rs
      domain_error.rs
      domain_event.rs
    modules/
      posting/
        entities/
        value_objects/
        policies/
        services/
        events/
      authentication/
      user_management/
      branch_management/
      audit_logs/
      dashboard/
      reports/
      ocr/
      notifications/
      synchronization/
  infrastructure/
    README.md
    config/
      app_config.rs
      environment.rs
    database/
      postgres/
      sqlite_cache/
      migrations/
    google/
      drive_client.rs
      sheets_client.rs
    python_bridge/
      process_client.rs
      sidecar_client.rs
    filesystem/
    logging/
    audit/
    cache/
    workers/
    sync/

src/
  renderer/
    app/
      App.tsx
      routes.tsx
      providers.tsx
    features/
      posting/
        presentation/
          pages/
          components/
          view-models/
        application/
          postingFacade.ts
          postingStore.ts
        api/
          postingApi.ts
        model/
          postingTypes.ts
      authentication/
      user-management/
      branch-management/
      audit-logs/
      dashboard/
      reports/
      ocr/
      notifications/
      synchronization/
    shared/
      api/
        simsoftApiClient.ts
        errors.ts
      ui/
        modal/
        table/
        form/
        primitives/
      state/
      config/
      lib/
      types/
```

## Module Responsibilities

| Module | Owns | Does Not Own |
| --- | --- | --- |
| posting | SIMSOFT parsing, preview building, duplicate/post locks, posting orchestration | UI layout, Google auth implementation |
| authentication | operator identity, Google OAuth state, auth guards | posting business rules |
| user management | admins, members, branch assignments, access requests | Google Sheets writes |
| branch management | branch index, branch folder scan, target branch selection rules | parsing Excel rows |
| audit logs | immutable audit records, batch IDs, operator traces | screen notifications |
| dashboard | aggregate app status, health summaries, read models | command side effects |
| reports | daily, receipt, SCR vs BR, accounts read models | low-level Google client details |
| OCR | receipt image ingestion, text extraction, OCR confidence | posting approval decisions |
| notifications | toast/system notifications, background job updates | domain validation |
| synchronization | offline queue, cloud sync, conflict resolution | feature-specific business logic |

## System Flow

```text
React view
  -> feature view model
  -> frontend API client
  -> Tauri command
  -> API DTO validation/auth guard
  -> application command handler/use case
  -> domain policies/entities
  -> repository/service ports
  -> infrastructure adapters
  -> database/filesystem/Google/Python bridge
```

## Event Flow

Use events for cross-module side effects. Commands change state; events announce what happened.

```text
PostPreviewCommand
  -> PostPreviewHandler
  -> PostingService
  -> emits PostingPreviewPosted
      -> AuditLogHandler writes audit record
      -> NotificationHandler publishes desktop update
      -> SyncHandler queues cloud synchronization
```

Recommended event names:

- `PostingFileParsed`
- `BranchFolderScanned`
- `PostingPreviewBuilt`
- `PostingPreviewPosted`
- `DuplicateHistoryReset`
- `OperatorSignedIn`
- `AccessConfigChanged`
- `OcrReceiptProcessed`
- `SyncJobQueued`
- `SyncJobFailed`

## Data Flow

```text
DTO input
  -> validation schema
  -> command object
  -> domain value objects/entities
  -> repository transaction
  -> DTO output
```

DTOs are transport contracts. Domain objects must not be shaped around React, Tauri, Google API responses, or SQL rows.

## Backend Standards

- Keep Tauri command functions thin: parse DTO, call application handler, map result/error.
- Put all business decisions in domain policies or application services.
- Wrap Google Drive/Sheets, filesystem, Python bridge, SQLite cache, and PostgreSQL behind ports.
- Use repository interfaces for persistence. Implement them in infrastructure.
- Use a Unit of Work for posting transactions: audit row, duplicate history, posting locks, and local sync queue must commit consistently.
- Centralize error mapping into typed categories: validation, authorization, conflict, external service, unavailable, internal.
- Background jobs must be idempotent and keyed by stable IDs such as branch ID, spreadsheet ID, file hash, or batch ID.
- Never let UI call a database, filesystem path, or Google client directly.

## Frontend Standards

- Feature folders own feature screens, view models, feature state, and API facades.
- Shared UI contains only reusable primitives, modal, table, and form systems.
- View models call feature application facades; components render state and dispatch intent.
- `window.simsoft` is accessed only through `shared/api/simsoftApiClient.ts`.
- Large tables must support pagination or virtualization before large posting volume is enabled.
- Routes should lazy-load feature modules.
- Modal state should be centralized through a reusable modal registry.
- Form validation should be declared in feature schema/view-model files, not embedded in JSX.

## Desktop Performance Rules

- Keep startup thin: load status, auth identity, and cached branch index only.
- Lazy-load reporting, OCR, advanced settings, and health-check screens.
- Move Google scans, OCR, and large Excel parsing to background workers/sidecars.
- Cache branch folder metadata and sheet stats with TTL and explicit refresh.
- Prefer incremental scans over full scans.
- Bound concurrency for Google, OCR, and filesystem jobs.
- Keep generated data in `data/`, `storage/`, or OS app-data paths, not source folders.

## Environment And Config

Central config should expose:

- `appEnv`: development, staging, production
- `storageMode`: local, shared-folder, postgres, hybrid
- `authMode`: service account or user OAuth
- `databaseUrl`
- `localCachePath`
- `googleServiceAccountJsonPath`
- `googleOauthClientJsonPath`
- `oauthTokenDir`
- `logDir`
- `syncEndpoint`
- `enableOcr`
- `enableCloudSync`
- `maxExcelFileMb`
- `workerConcurrency`

Config load order:

```text
compiled defaults
  -> .env
  -> environment variables
  -> admin settings file
  -> command-line/runtime overrides
```

## Incremental Migration Plan

1. Freeze current contracts.
   - Keep `src/shared/types.ts` and `window.simsoft` method names stable.
   - Add tests around current posting commands before moving implementation.

2. Create frontend API boundary.
   - Move direct `window.simsoft` usage into `src/renderer/shared/api/simsoftApiClient.ts`.
   - Update services/hooks to depend on the API client interface.

3. Split the dashboard hook.
   - Extract auth, branch scan, parsing, preview, posting, duplicate history, and modal state into feature view-model hooks.
   - Keep `useSimsoftDashboard` as a compatibility composer until the UI is migrated.

4. Split Tauri command modules.
   - Move validation into `src-tauri/src/api/validation.rs`.
   - Move path/config helpers into `src-tauri/src/infrastructure/config.rs`.
   - Move Python bridge process code into `src-tauri/src/infrastructure/python_bridge.rs`.
   - Keep command names unchanged.

5. Introduce application ports.
   - Define posting, auth, branch, audit, cache, config, and Google ports.
   - Adapt current Python bridge calls behind those ports.

6. Extract domain policies.
   - Move branch assignment, posting confirmation, file validation, duplicate policy, and post-lock rules into pure domain modules.

7. Add worker queue.
   - Start with in-process async jobs for scan/preview/post.
   - Later replace with a long-lived sidecar or service without changing application handlers.

8. Add PostgreSQL support.
   - Keep local cache SQLite/JSON for offline mode.
   - Add repositories that can write audit logs, users, branches, sync queue, and posting batches to PostgreSQL.

9. Add sync and OCR modules.
   - OCR produces reviewed receipt artifacts.
   - Synchronization consumes domain events and queued mutations.

10. Prepare microservice extraction.
    - Each application module already communicates through commands, events, DTOs, and ports.
    - Move modules out-of-process only after local-first behavior is stable.

## Implemented Architecture Increments

- Tauri command registration is separated from API commands, validation, config, logging, and Python bridge infrastructure.
- Renderer backend access is centralized through `src/renderer/shared/api/simsoftApiClient.ts`.
- Posting frontend view-model derivations live in `src/renderer/features/posting/model/postingViewModel.ts`.
- Python posting workflow now accepts injected application ports:
  - `GoogleSheetsGateway`
  - `AuditRepository`
  - `PostingTransactionManager`
  - `EventBus`
- Default Python adapters preserve the current local-first behavior:
  - Google Sheets writes still use the existing Google client implementation.
  - Audit logs still write local CSV audit records.
  - Duplicate history and branch locks still use the existing local CSV/JSON store.
- Posting workflow now publishes application events:
  - `PostingPreviewBuilt`
  - `PostingPreviewAuditWritten`
  - `PostingPreviewPosted`
  - `PostingFinalAuditWritten`
  - `DuplicateHistoryRecorded`
- Rust now uses a long-lived Python bridge sidecar by default instead of spawning Python for every command.
  - The sidecar speaks newline-delimited JSON over stdin/stdout.
  - If the sidecar fails or exits unexpectedly, Rust clears it and falls back to one-shot bridge execution for the current command.
  - Set `SIMSOFT_DISABLE_PYTHON_SIDECAR=1` to force legacy one-shot bridge behavior for troubleshooting.

## Architectural Problems Detected

- `src-tauri/src/lib.rs` mixes command routing, validation, access control, paths, logging, support-folder opening, health checks, and Python process invocation.
- `src/renderer/hooks/useSimsoftDashboard.ts` mixes auth state, posting flow, branch filtering, modal state, table derivation, toast timers, and workflow actions.
- `src/renderer/components/dashboard/Workspace.tsx` and `AdvancedSettingsPage.tsx` are large UI files that should be split by feature/view model.
- Renderer services still depend on the global `window.simsoft` instead of an injectable API boundary.
- Python `workflow_service.py` coordinates parsing, Google clients, audit, duplicate handling, sheet read/write, and cache concerns in one service.
- Business rules are distributed across React, Rust validation, Python workflow, and Python core modules.
- Google Sheets integration is partly business-facing rather than fully hidden behind application ports.
- Generated artifacts and build outputs live beside active source, which slows repo scanning and increases accidental coupling.

## Production Compatibility

- Keep all runtime data paths configurable for Windows non-developer PCs.
- Package Python bridge/sidecar as a Tauri resource until Rust-native infrastructure replaces it.
- Avoid requiring developer tools after install.
- Keep installer and portable builds reading config from app-data/shared configured paths.
- Future mobile/API clients should call the same application DTOs through HTTP instead of Tauri IPC.
