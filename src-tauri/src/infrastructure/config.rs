use serde_json::Value;
use std::{
  env, fs,
  path::{Path, PathBuf},
  time::{SystemTime, UNIX_EPOCH},
};

pub fn workspace_root() -> PathBuf {
  let dev_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
    .parent()
    .unwrap_or_else(|| Path::new("."))
    .to_path_buf();
  if cfg!(debug_assertions) && dev_root.join("scripts").join("python_bridge.py").exists() {
    return dev_root;
  }
  env::current_exe()
    .ok()
    .and_then(|path| path.parent().map(Path::to_path_buf))
    .unwrap_or_else(|| PathBuf::from("."))
}

pub fn path_string(path: impl AsRef<Path>) -> String {
  path.as_ref().to_string_lossy().to_string()
}

fn configured_config_dir() -> Option<PathBuf> {
  env::var("SIMSOFT_CONFIG_DIR")
    .ok()
    .map(|value| value.trim().to_string())
    .filter(|value| !value.is_empty() && !value.contains('\0'))
    .map(PathBuf::from)
}

fn local_app_data_root() -> PathBuf {
  env::var("LOCALAPPDATA")
    .map(PathBuf::from)
    .unwrap_or_else(|_| workspace_root())
    .join("SIMSOFT Posting")
}

pub fn runtime_config_dir() -> PathBuf {
  if let Some(path) = configured_config_dir() {
    return path;
  }
  local_app_data_root().join("config")
}

pub fn config_path(file_name: &str) -> String {
  let env_key = match file_name {
    "service_account.json" => "SIMSOFT_SERVICE_ACCOUNT_JSON_PATH",
    "oauth_client.json" => "SIMSOFT_OAUTH_CLIENT_JSON_PATH",
    _ => "",
  };
  if !env_key.is_empty() {
    if let Ok(value) = env::var(env_key) {
      if !value.trim().is_empty() {
        return value;
      }
    }
  }
  let root = workspace_root();
  let config_dir = runtime_config_dir();
  let mut candidates = vec![config_dir.join(file_name)];
  if cfg!(debug_assertions) {
    candidates.push(root.join("config").join(file_name));
  }
  if file_name == "oauth_client.json" || file_name.ends_with(".example.json") {
    candidates.push(root.join("config").join(file_name));
    candidates.push(root.join("_up_").join("config").join(file_name));
    candidates.push(root.join("resources").join("_up_").join("config").join(file_name));
    candidates.push(root.join("resources").join("config").join(file_name));
  }
  candidates
    .into_iter()
    .find(|path| path.exists())
    .map(path_string)
    .unwrap_or_else(|| path_string(config_dir.join(file_name)))
}

fn runtime_data_root() -> PathBuf {
  let portable_data = workspace_root().join("data");
  if portable_data.exists() {
    portable_data
  } else {
    local_app_data_root().join("data")
  }
}

pub fn data_path(file_name: &str) -> String {
  let env_key = match file_name {
    "duplicate_history.csv" => "SIMSOFT_DUPLICATE_HISTORY_PATH",
    "posted_batches.csv" => "SIMSOFT_POSTED_BATCHES_PATH",
    "posting_locks.json" => "SIMSOFT_POSTING_LOCKS_PATH",
    "access_control.json" => "SIMSOFT_ACCESS_CONTROL_PATH",
    _ => "",
  };
  if !env_key.is_empty() {
    if let Ok(value) = env::var(env_key) {
      if !value.trim().is_empty() {
        return value;
      }
    }
  }
  path_string(runtime_data_root().join(file_name))
}

pub fn auth_mode() -> String {
  env::var("SIMSOFT_AUTH_MODE")
    .ok()
    .filter(|value| value == "service_account")
    .unwrap_or_else(|| "user_oauth".to_string())
}

pub fn runtime_log_dir() -> PathBuf {
  if let Ok(value) = env::var("SIMSOFT_LOG_DIR") {
    return PathBuf::from(value);
  }
  let portable_logs = workspace_root().join("logs");
  if portable_logs.exists() {
    portable_logs
  } else {
    local_app_data_root().join("logs")
  }
}

pub fn runtime_oauth_token_dir() -> String {
  env::var("SIMSOFT_OAUTH_TOKEN_DIR").unwrap_or_else(|_| path_string(runtime_data_root().join("oauth_tokens")))
}

pub fn runtime_log_dir_string() -> String {
  path_string(runtime_log_dir())
}

fn read_json_object(path: &Path) -> Result<Value, String> {
  let metadata = path.metadata().map_err(|_| "File is missing.".to_string())?;
  if !metadata.is_file() {
    return Err("Path is not a file.".to_string());
  }
  if metadata.len() > 2 * 1024 * 1024 {
    return Err("File is larger than the 2 MB credential limit.".to_string());
  }
  let raw = fs::read_to_string(path).map_err(|_| "File could not be read.".to_string())?;
  let parsed: Value = serde_json::from_str(&raw).map_err(|_| "File is not valid JSON.".to_string())?;
  if !parsed.is_object() {
    return Err("Credential JSON must be an object.".to_string());
  }
  Ok(parsed)
}

fn validate_service_account(path: &Path) -> Result<(), String> {
  let parsed = read_json_object(path)?;
  let account_type = parsed.get("type").and_then(Value::as_str).unwrap_or_default();
  let client_email = parsed.get("client_email").and_then(Value::as_str).unwrap_or_default();
  let private_key = parsed.get("private_key").and_then(Value::as_str).unwrap_or_default();
  if account_type != "service_account" || client_email.is_empty() || private_key.is_empty() {
    return Err("Service account JSON is missing required Google credential fields.".to_string());
  }
  Ok(())
}

fn validate_oauth_client(path: &Path) -> Result<(), String> {
  let parsed = read_json_object(path)?;
  let client = parsed
    .get("installed")
    .or_else(|| parsed.get("web"))
    .ok_or_else(|| "OAuth client JSON must contain an installed or web client.".to_string())?;
  let client_id = client.get("client_id").and_then(Value::as_str).unwrap_or_default();
  let auth_uri = client.get("auth_uri").and_then(Value::as_str).unwrap_or_default();
  let token_uri = client.get("token_uri").and_then(Value::as_str).unwrap_or_default();
  if client_id.is_empty() || auth_uri.is_empty() || token_uri.is_empty() {
    return Err("OAuth client JSON is missing required Google OAuth fields.".to_string());
  }
  Ok(())
}

pub fn credential_status(auth_mode_value: &str) -> (bool, Vec<Value>) {
  let config_dir = runtime_config_dir();
  let required = if auth_mode_value == "service_account" {
    vec!["service_account.json"]
  } else {
    vec!["oauth_client.json"]
  };
  let mut items = Vec::new();
  for file_name in ["oauth_client.json", "service_account.json"] {
    let path = PathBuf::from(config_path(file_name));
    let required_file = required.contains(&file_name);
    let result = if path.exists() {
      match file_name {
        "oauth_client.json" => validate_oauth_client(&path),
        "service_account.json" => validate_service_account(&path),
        _ => Ok(()),
      }
    } else if required_file {
      Err("Required credential file is missing.".to_string())
    } else {
      Ok(())
    };
    let ok = result.is_ok();
    items.push(serde_json::json!({
      "fileName": file_name,
      "path": path_string(&path),
      "required": required_file,
      "ok": ok,
      "message": result.err().unwrap_or_else(|| if path.exists() { "Ready".to_string() } else { "Optional file not found.".to_string() })
    }));
  }
  let ready = items
    .iter()
    .all(|item| !item.get("required").and_then(Value::as_bool).unwrap_or(false) || item.get("ok").and_then(Value::as_bool).unwrap_or(false));
  let _ = fs::create_dir_all(config_dir);
  (ready, items)
}

pub fn now_timestamp() -> String {
  SystemTime::now()
    .duration_since(UNIX_EPOCH)
    .map(|duration| duration.as_secs().to_string())
    .unwrap_or_else(|_| "0".to_string())
}
