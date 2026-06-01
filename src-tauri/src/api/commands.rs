use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{env, fs, path::{Path, PathBuf}, process::Command};

use super::validation::{
  is_safe_email, read_access_config, require_admin, validate_access_config, validate_excel_file_path,
  validate_excel_file_paths, validate_google_folder_url, validate_google_payload, validate_operator_identity, validate_operator_payload,
  value_array, value_object, write_access_config,
};
use crate::infrastructure::config::{
  auth_mode, config_path, credential_status, data_path, now_timestamp, path_string, runtime_config_dir,
  runtime_log_dir, runtime_log_dir_string, runtime_oauth_token_dir, workspace_root,
};
use crate::infrastructure::python_bridge::{
  fallback_operator, packaged_bridge_executable, python_bridge_payload, python_executable, restart_python_sidecar,
};

#[derive(Serialize)]
pub struct ShellStatus {
  app_name: &'static str,
  shell: &'static str,
}

#[derive(Deserialize)]
pub struct AccessRequestInput {
  email: Option<String>,
  name: Option<String>,
}

#[tauri::command]
pub fn shell_status() -> ShellStatus {
  ShellStatus {
    app_name: "SIMSOFT Posting",
    shell: "tauri",
  }
}

#[tauri::command]
pub fn app_get_status() -> Value {
  let access = read_access_config();
  let mode = auth_mode();
  let (config_ready, credential_items) = credential_status(&mode);
  let shared_storage_configured = env::var("SIMSOFT_DUPLICATE_HISTORY_PATH").is_ok()
    || env::var("SIMSOFT_POSTED_BATCHES_PATH").is_ok()
    || env::var("SIMSOFT_POSTING_LOCKS_PATH").is_ok()
    || env::var("SIMSOFT_ACCESS_CONTROL_PATH").is_ok()
    || env::var("SIMSOFT_LOG_DIR").is_ok();
  json!({
    "appName": "SIMSOFT Posting",
    "appVersion": env!("CARGO_PKG_VERSION"),
    "authMode": mode,
    "configDir": path_string(runtime_config_dir()),
    "configReady": config_ready,
    "credentialStatus": credential_items,
    "cachePath": data_path("cache/simsoft_cache.sqlite"),
    "duplicateHistoryPath": data_path("duplicate_history.csv"),
    "postedBatchesPath": data_path("posted_batches.csv"),
    "postingLocksPath": data_path("posting_locks.json"),
    "accessControlPath": data_path("access_control.json"),
    "logDir": runtime_log_dir_string(),
    "serviceAccountJsonPath": config_path("service_account.json"),
    "oauthClientJsonPath": config_path("oauth_client.json"),
    "oauthTokenDir": runtime_oauth_token_dir(),
    "adminEmails": value_array(&access, "adminEmails"),
    "memberEmails": value_array(&access, "memberEmails"),
    "userBranches": value_object(&access, "userBranches"),
    "knownOperators": value_array(&access, "knownOperators"),
    "accessRequests": value_array(&access, "accessRequests"),
    "livePostingSource": "python-core-settings",
    "bullMqEnabled": false,
    "requireUserOAuthForPosting": env::var("SIMSOFT_REQUIRE_USER_OAUTH_FOR_POSTING").is_ok(),
    "sharedStorageConfigured": shared_storage_configured,
    "cloudEndpointConfigured": false
  })
}

#[tauri::command]
pub fn app_request_access(input: AccessRequestInput) -> Value {
  let email = input.email.unwrap_or_default().trim().to_lowercase();
  let name = input.name.unwrap_or_default().trim().chars().take(80).collect::<String>();
  if !is_safe_email(&email) {
    return json!({ "ok": false, "url": "", "recipients": [], "error": "Enter a valid Google email address." });
  }
  let mut access = read_access_config();
  let recipients = value_array(&access, "adminEmails");
  let request = json!({
    "email": email,
    "name": name,
    "requestedAt": now_timestamp(),
    "lastRequestedAt": now_timestamp(),
    "status": "pending"
  });
  let mut requests = value_array(&access, "accessRequests").as_array().cloned().unwrap_or_default();
  requests.retain(|item| item.get("email") != request.get("email"));
  requests.push(request);
  access["accessRequests"] = Value::Array(requests);
  match write_access_config(&access) {
    Ok(()) => json!({ "ok": true, "url": "", "recipients": recipients }),
    Err(error) => json!({ "ok": false, "url": "", "recipients": recipients, "error": error }),
  }
}

#[tauri::command]
pub fn app_save_access_config(input: Value, operator_identity: Option<Value>) -> Result<Value, String> {
  require_admin(&operator_identity)?;
  validate_access_config(&input)?;
  let current = read_access_config();
  let next = json!({
    "adminEmails": value_array(&input, "adminEmails"),
    "memberEmails": value_array(&input, "memberEmails"),
    "userBranches": value_object(&input, "userBranches"),
    "knownOperators": value_array(&current, "knownOperators"),
    "accessRequests": value_array(&input, "accessRequests")
  });
  write_access_config(&next)?;
  Ok(app_get_status())
}

#[tauri::command]
pub fn app_open_google_test_users_page(operator_identity: Option<Value>) -> Result<Value, String> {
  require_admin(&operator_identity)?;
  let url = "https://console.cloud.google.com/auth/audience";
  match open::that(url) {
    Ok(()) => Ok(json!({ "ok": true, "url": url })),
    Err(error) => Ok(json!({ "ok": false, "url": url, "error": error.to_string() })),
  }
}

#[tauri::command]
pub fn app_open_support_folder(kind: String, operator_identity: Option<Value>) -> Result<Value, String> {
  let (config_ready, _) = credential_status(&auth_mode());
  if kind == "config" && config_ready {
    require_admin(&operator_identity)?;
  } else if kind == "logs" {
    require_admin(&operator_identity)?;
  } else if kind != "config" {
    validate_operator_identity(&operator_identity)?;
  }
  let path = match kind.as_str() {
    "config" => runtime_config_dir(),
    "logs" => runtime_log_dir(),
    "data" => PathBuf::from(data_path("duplicate_history.csv")).parent().map(Path::to_path_buf).unwrap_or_else(|| workspace_root().join("data")),
    _ => return Err("Invalid support folder.".to_string()),
  };
  let _ = fs::create_dir_all(&path);
  match open::that(&path) {
    Ok(()) => Ok(json!({ "ok": true, "path": path_string(path) })),
    Err(error) => Ok(json!({ "ok": false, "path": path_string(path), "error": error.to_string() })),
  }
}

#[tauri::command]
pub fn app_health_check() -> Value {
  let root = workspace_root();
  let mode = auth_mode();
  let (config_ready, credential_items) = credential_status(&mode);
  let items = vec![
    json!({
      "label": "Python bridge",
      "ok": packaged_bridge_executable().is_some() || root.join("scripts").join("python_bridge.py").exists(),
      "detail": packaged_bridge_executable().map(path_string).unwrap_or_else(|| path_string(root.join("scripts").join("python_bridge.py")))
    }),
    json!({
      "label": "Python executable",
      "ok": packaged_bridge_executable().is_some() || Command::new(python_executable()).arg("--version").output().is_ok(),
      "detail": if packaged_bridge_executable().is_some() { "Bundled Python bridge".to_string() } else { python_executable() }
    }),
    json!({"label": "Credential configuration", "ok": config_ready, "detail": path_string(runtime_config_dir())}),
    json!({"label": "Google service account", "ok": credential_items.iter().find(|item| item.get("fileName").and_then(Value::as_str) == Some("service_account.json")).and_then(|item| item.get("ok")).and_then(Value::as_bool).unwrap_or(false), "detail": config_path("service_account.json")}),
    json!({"label": "OAuth client", "ok": credential_items.iter().find(|item| item.get("fileName").and_then(Value::as_str) == Some("oauth_client.json")).and_then(|item| item.get("ok")).and_then(Value::as_bool).unwrap_or(false), "detail": config_path("oauth_client.json")}),
    json!({"label": "Data folder", "ok": PathBuf::from(data_path("duplicate_history.csv")).parent().map(Path::exists).unwrap_or(false), "detail": PathBuf::from(data_path("duplicate_history.csv")).parent().map(path_string).unwrap_or_default()}),
    json!({"label": "Duplicate history", "ok": PathBuf::from(data_path("duplicate_history.csv")).exists(), "detail": data_path("duplicate_history.csv")}),
    json!({"label": "Log folder", "ok": PathBuf::from(runtime_log_dir_string()).exists(), "detail": runtime_log_dir_string()})
  ];
  let ok = items.iter().all(|item| item.get("ok").and_then(Value::as_bool).unwrap_or(false));
  json!({ "checkedAt": now_timestamp(), "ok": ok, "items": items })
}

#[tauri::command]
pub fn dialog_choose_simsoft_file() -> Option<String> {
  rfd::FileDialog::new()
    .add_filter("Excel Workbooks", &["xlsx", "xlsm"])
    .pick_file()
    .map(path_string)
}

#[tauri::command]
pub fn dialog_choose_simsoft_files() -> Vec<String> {
  rfd::FileDialog::new()
    .add_filter("Excel Workbooks", &["xlsx", "xlsm"])
    .pick_files()
    .unwrap_or_default()
    .into_iter()
    .map(path_string)
    .collect()
}

#[tauri::command]
pub fn simsoft_parse_file(file_path: String) -> Result<Value, String> {
  let safe_path = validate_excel_file_path(&file_path)?;
  python_bridge_payload("parse_simsoft", json!({ "filePath": safe_path }))
}

#[tauri::command]
pub fn simsoft_parse_files(input: Value) -> Result<Value, String> {
  let safe_paths = validate_excel_file_paths(&input)?;
  python_bridge_payload("parse_simsoft", json!({ "filePath": safe_paths.first().cloned().unwrap_or_default(), "filePaths": safe_paths }))
}

#[tauri::command]
pub fn google_scan_folder(mut input: Value) -> Result<Value, String> {
  if !input.is_object() {
    return Err("Google folder data is required.".to_string());
  }
  validate_operator_payload(&input)?;
  let folder_url = validate_google_folder_url(input.get("folderUrl").unwrap_or(&Value::Null))?;
  input["folderUrl"] = Value::String(folder_url);
  python_bridge_payload("scan_google_folder", input)
}

#[tauri::command]
pub fn google_build_previews(mut input: Value) -> Result<Value, String> {
  validate_google_payload(&mut input, true, false)?;
  python_bridge_payload("build_google_previews", input)
}

#[tauri::command]
pub fn google_get_sheet_stats(mut input: Value) -> Result<Value, String> {
  validate_google_payload(&mut input, false, false)?;
  python_bridge_payload("google_sheet_stats", input)
}

#[tauri::command]
pub fn google_post_previews(mut input: Value) -> Result<Value, String> {
  let operator_identity = input.get("operatorIdentity").cloned();
  require_admin(&operator_identity)?;
  validate_google_payload(&mut input, true, true)?;
  python_bridge_payload("post_google_previews", input)
}

#[tauri::command]
pub fn operator_get_identity() -> Value {
  python_bridge_payload("operator_identity", json!({})).unwrap_or_else(|error| fallback_operator(Some(error)))
}

#[tauri::command]
pub fn operator_login_google() -> Value {
  python_bridge_payload("operator_login_google", json!({})).unwrap_or_else(|error| fallback_operator(Some(error)))
}

#[tauri::command]
pub fn operator_logout_google() -> Value {
  python_bridge_payload("operator_logout_google", json!({})).unwrap_or_else(|error| fallback_operator(Some(error)))
}

#[tauri::command]
pub fn duplicates_get_status() -> Value {
  python_bridge_payload("duplicate_history_status", json!({})).unwrap_or_else(|error| {
    json!({
      "duplicateHistoryPath": data_path("duplicate_history.csv"),
      "duplicateTransactionCount": 0,
      "postedBatchRowCount": 0,
      "error": error
    })
  })
}

#[tauri::command]
pub fn duplicates_reset(confirmation: String, operator_identity: Option<Value>) -> Result<Value, String> {
  require_admin(&operator_identity)?;
  if confirmation != "Reset Duplicate History" {
    return Err("Reset confirmation is required.".to_string());
  }
  python_bridge_payload("reset_duplicate_history", json!({ "confirmation": confirmation }))
}

#[tauri::command]
pub fn cache_clear(operator_identity: Option<Value>) -> Result<Value, String> {
  require_admin(&operator_identity)?;
  let mut removed = Vec::new();
  for path in [
    PathBuf::from(data_path("cache/branch_index.json")),
    PathBuf::from(data_path("cache/simsoft_cache.sqlite")),
    PathBuf::from(format!("{}-wal", data_path("cache/simsoft_cache.sqlite"))),
    PathBuf::from(format!("{}-shm", data_path("cache/simsoft_cache.sqlite"))),
  ] {
    if path.exists() {
      fs::remove_file(&path).map_err(|error| format!("Cache file could not be removed: {error}"))?;
      removed.push(path_string(path));
    }
  }
  let python_result = python_bridge_payload("clear_cache", json!({})).unwrap_or_else(|error| {
    json!({ "ok": false, "error": error })
  });
  restart_python_sidecar();
  Ok(json!({ "ok": true, "removed": removed, "python": python_result }))
}
