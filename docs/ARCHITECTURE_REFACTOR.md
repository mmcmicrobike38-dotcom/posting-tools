# Architecture Refactor Blueprint

## Current Weaknesses

- **Presentation and runtime coupling**: native shell command handlers can become overloaded if windowing, access control, dialogs, support-folder opening, and workflow orchestration are kept in one module.
- **Application and infrastructure coupling**: `SimsoftWorkflow` directly coordinates filesystem validation, SQLite cache access, Excel parsing, Python subprocess calls, logging, and Google workflow calls.
- **Runtime-specific imports in backend code**: backend modules should use runtime-neutral resource adapters so desktop packaging details do not leak into business logic.
- **Scanning boundaries are mixed**: Drive scanning, local file indexing, caching, progress reporting, and duplicate prevention are not yet exposed through one consistent pipeline contract.
- **Generated clutter at repo root**: `.pytest-*`, build output, and packaged app folders obscure active source and slow broad tooling scans.

## Target Layered Architecture

```text
apps/
  desktop/                      Tauri shell and desktop UI entry
  automation/                   automation/CLI entrypoints

backend/
  api/                          desktop command handlers, auth guards, DTO validation
  application/                  use-cases: parse, scan, preview, post, cleanup
  domain/                       business rules, entities, pure transforms
  infrastructure/               SQLite, filesystem, Google, Python bridge, process adapters
  workers/                      bounded queues, background jobs, progress/cancel handling
  python-workers/               Python bridge compatibility
  receipt-engine/               receipt/image processing pipeline

packages/
  shared-ui/                    reusable React components
  shared-utils/                 cross-runtime utility functions
  shared-types/                 API and domain contracts

storage/
  cache/
  temp/
  receipts/
    originals/
    compressed/
    thumbnails/

infra/
  database/
  scripts/
  cleanup/
```

## Recommended Refactor Sequence

1. **Extract command handlers from the Tauri shell**
   - Move IPC command bodies into `backend/api`.
   - Keep shell-specific code limited to window/dialog/open-external adapters.
   - Benefit: Tauri commands stay thin and application services remain testable.

2. **Define application services**
   - Split `SimsoftWorkflow` into use-case classes:
     - `ParseSimsoftFileService`
     - `ScanBranchFolderService`
     - `BuildPreviewService`
     - `PostPreviewService`
     - `OperatorAuthService`
   - Benefit: smaller modules, easier tests, cleaner performance instrumentation.

3. **Move business rules into domain modules**
   - Keep branch ID detection, duplicate policy, posting validation, and receipt rules pure.
   - Benefit: business behavior becomes testable without Tauri, SQLite, or Google.

4. **Introduce infrastructure adapters**
   - Wrap SQLite, Google Drive, Google Sheets, Python bridge, filesystem, and runtime resources behind interfaces.
   - Benefit: sidecars, workers, and Tauri commands can swap implementations without changing business logic.

5. **Standardize scanning pipelines**
   - Use a generic pipeline shape:
     - source enumerates items
     - index store checks freshness
     - processors transform changed items
     - sink persists results
   - Benefit: branch folder scans, local receipt scans, and future scan types share queueing, caching, and progress behavior.

6. **Move heavy work to workers**
   - Use bounded queues for image processing, recursive filesystem indexing, and Google metadata requests.
   - Deduplicate jobs by stable keys.
   - Benefit: avoids UI blocking, CPU spikes, and duplicate scan storms.

7. **Keep Tauri command parity**
   - Keep all existing `window.simsoft` methods backed by Tauri commands or a Node/Python sidecar.
   - Benefit: preserves features while keeping the lighter Tauri runtime.

## Scanning Architecture

```text
UI action / watcher event
  -> backend/api scan command
  -> application scan use-case
  -> ScanPipeline
      -> ScanSource: local directory / Google Drive folder / receipt batch
      -> IndexStore: SQLite or JSON cache
      -> JobQueue: bounded concurrency and de-dupe
      -> Processor: branch indexer / receipt thumbnailer / parser
      -> ResultStore: cache, previews, logs
```

## Scalability Improvements

- **Bounded concurrency** prevents thousands of files from becoming thousands of simultaneous promises.
- **Incremental indexing** skips unchanged files by size and modified time.
- **Debounced watchers** collapse filesystem event bursts into one batch.
- **Job de-duplication** prevents duplicate scans of the same folder or receipt.
- **Storage separation** keeps generated thumbnails/compressed receipts out of source folders.
- **Runtime-neutral services** let desktop, automation, and future API processes share the same business behavior.

## Bottlenecks To Watch

- Python bridge currently starts a new subprocess per command. For high-volume workflows, move to a long-lived sidecar protocol.
- Receipt compression currently has a pipeline seam but no native image transform dependency yet.
- Google Drive scans depend on API latency and quota; keep metadata-only scans and cache aggressively.
- Renderer state currently owns scan caching too. Backend should become the authoritative cache for multi-window or automation use.
