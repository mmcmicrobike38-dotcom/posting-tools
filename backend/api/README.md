# Backend API Layer

Transport boundary for desktop commands and future HTTP handlers.

Rules:

- Tauri command functions should stay thin.
- Validate DTOs and permissions here.
- Call application command/query handlers.
- Map application errors into Tauri/HTTP friendly responses.
