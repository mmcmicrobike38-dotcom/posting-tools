# Backend Application Layer

Use cases, command handlers, event handlers, validation orchestration, and port definitions live here.

Rules:

- Depends on `backend/domain`.
- Defines ports that infrastructure implements.
- Does not import Tauri, React, Google SDKs, filesystem APIs, SQL clients, or Python subprocess code directly.
- Owns transactions through a Unit of Work abstraction.
