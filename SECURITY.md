# SIMSOFT Security Guide

## Enterprise Mode

For production environments where Google Sheet edit history must identify the real operator, set:

```env
SIMSOFT_AUTH_MODE=user_oauth
SIMSOFT_REQUIRE_USER_OAUTH_FOR_POSTING=true
```

With this policy enabled, Google preview and posting requests are blocked unless a Google operator is signed in through OAuth.

## Secrets At Rest

- Google OAuth user tokens are stored under `data/oauth_tokens`.
- On Windows, OAuth token JSON is encrypted with Windows DPAPI for the current OS user before writing to disk.
- Service account keys and OAuth client JSON files must remain outside source control.
- `.gitignore` excludes real local credential files and token folders.

## Runtime Boundaries

- The Tauri renderer runs without Node integration and talks to native code through explicit Tauri commands.
- Native command handlers validate Google folder links, Excel file paths, branch scan data, auth mode, operator identity, and duplicate reset confirmations before calling the backend workflow.
- Sensitive logger metadata such as tokens, private keys, client secrets, API keys, and authorization headers is redacted before it is written.

## Production Build Checklist

1. Use `SIMSOFT_REQUIRE_USER_OAUTH_FOR_POSTING=true` for operator-attributed Google Sheet history.
2. Keep `config/service_account.json`, `config/oauth_client.json`, and `data/oauth_tokens` local and private.
3. Run `npm run build` and Python tests before packaging.
4. Rebuild native modules after Node, Rust, or Tauri upgrades.
5. Code-sign release builds in a signing-enabled production environment.
