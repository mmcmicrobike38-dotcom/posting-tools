# Workers

Background workers for scans, file indexing, receipt processing, and other CPU or IO-heavy jobs.

Workers should never block the renderer. Jobs should be deduplicated by stable keys and use bounded concurrency.

