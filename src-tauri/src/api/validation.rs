use serde_json::{json, Value};
use std::{env, fs, path::PathBuf};

use crate::infrastructure::config::{data_path, path_string};

pub fn read_access_config() -> Value {
  let path = PathBuf::from(data_path("access_control.json"));
  fs::read_to_string(path)
    .ok()
    .and_then(|raw| serde_json::from_str::<Value>(&raw).ok())
    .unwrap_or_else(|| {
      json!({
        "adminEmails": [],
        "memberEmails": [],
        "userBranches": {},
        "knownOperators": [],
        "accessRequests": []
      })
    })
}

pub fn write_access_config(input: &Value) -> Result<(), String> {
  let path = PathBuf::from(data_path("access_control.json"));
  if let Some(parent) = path.parent() {
    fs::create_dir_all(parent).map_err(|error| format!("Access config folder could not be created: {error}"))?;
  }
  let body = serde_json::to_string_pretty(input).map_err(|error| format!("Access config could not be encoded: {error}"))?;
  fs::write(path, body).map_err(|error| format!("Access config could not be saved: {error}"))
}

pub fn value_array(config: &Value, key: &str) -> Value {
  config.get(key).cloned().filter(Value::is_array).unwrap_or_else(|| json!([]))
}

pub fn value_object(config: &Value, key: &str) -> Value {
  config.get(key).cloned().filter(Value::is_object).unwrap_or_else(|| json!({}))
}

pub fn value_str<'a>(value: &'a Value, key: &str) -> &'a str {
  value.get(key).and_then(Value::as_str).unwrap_or_default()
}

pub fn is_safe_email(value: &str) -> bool {
  let email = value.trim();
  email.len() <= 254
    && email.contains('@')
    && email.contains('.')
    && !email.contains(char::is_whitespace)
    && !email.contains('\n')
    && !email.contains('\r')
}

fn is_safe_branch_id(value: &str) -> bool {
  let len = value.len();
  (3..=32).contains(&len) && value.chars().all(|ch| ch.is_ascii_alphanumeric() || ch == '_' || ch == '-')
}

fn is_safe_sheet_id(value: &str) -> bool {
  value.len() >= 20 && value.chars().all(|ch| ch.is_ascii_alphanumeric() || ch == '_' || ch == '-')
}

fn env_u64(name: &str, fallback: u64) -> u64 {
  env::var(name)
    .ok()
    .and_then(|value| value.parse::<u64>().ok())
    .filter(|value| *value > 0)
    .unwrap_or(fallback)
}

pub fn validate_google_folder_url(value: &Value) -> Result<String, String> {
  let url = value.as_str().unwrap_or_default().trim();
  if url.is_empty() {
    return Err("Google Drive branch folder link is required.".to_string());
  }
  if url.len() > 2048 || !url.starts_with("https://") || url.contains('\n') || url.contains('\r') {
    return Err("Paste a valid Google Drive folder link.".to_string());
  }
  let without_scheme = url.trim_start_matches("https://");
  let host = without_scheme
    .split(['/', '?', '#'])
    .next()
    .unwrap_or_default()
    .trim_start_matches("www.");
  let path_and_query = without_scheme.strip_prefix(host).unwrap_or_default();
  if host.contains('@') || host.contains(':') {
    return Err("Paste a valid Google Drive folder link.".to_string());
  }
  let valid_host = host == "drive.google.com" || host == "docs.google.com";
  let has_folder_path = host == "drive.google.com" && path_and_query.contains("/drive/folders/");
  let has_folder_param = host == "docs.google.com" && path_and_query.contains("folder=");
  if !valid_host || (!has_folder_path && !has_folder_param) {
    return Err("Paste a valid Google Drive folder link.".to_string());
  }
  Ok(url.split('#').next().unwrap_or(url).to_string())
}

pub fn validate_excel_file_path(file_path: &str) -> Result<String, String> {
  let trimmed = file_path.trim();
  if trimmed.is_empty() || trimmed.contains('\0') {
    return Err("SIMSOFT Excel file is required.".to_string());
  }
  let path = PathBuf::from(trimmed);
  let resolved = path
    .canonicalize()
    .map_err(|_| "SIMSOFT Excel file does not exist.".to_string())?;
  if !resolved.is_file() {
    return Err("SIMSOFT Excel file does not exist.".to_string());
  }
  let extension = resolved
    .extension()
    .and_then(|value| value.to_str())
    .unwrap_or_default()
    .to_ascii_lowercase();
  if extension != "xlsx" && extension != "xlsm" {
    return Err("Only .xlsx and .xlsm files can be parsed.".to_string());
  }
  let max_mb = env_u64("SIMSOFT_MAX_EXCEL_FILE_MB", 50);
  let max_bytes = max_mb * 1024 * 1024;
  let size = resolved
    .metadata()
    .map_err(|_| "SIMSOFT Excel file does not exist.".to_string())?
    .len();
  if size > max_bytes {
    return Err(format!("Excel file is larger than the configured {max_mb} MB limit."));
  }
  Ok(path_string(resolved))
}

pub fn validate_excel_file_paths(input: &Value) -> Result<Vec<String>, String> {
  if let Some(items) = input.get("filePaths").and_then(Value::as_array) {
    if items.is_empty() {
      return Err("Choose at least one SIMSOFT Excel file.".to_string());
    }
    let max_count = env_u64("SIMSOFT_MAX_EXCEL_FILE_COUNT", 25) as usize;
    if items.len() > max_count {
      return Err(format!("Choose {max_count} SIMSOFT Excel files or fewer."));
    }
    let paths: Vec<String> = items
      .iter()
      .map(|item| validate_excel_file_path(item.as_str().unwrap_or_default()))
      .collect::<Result<Vec<String>, String>>()?;
    let unique_count = paths.iter().collect::<std::collections::BTreeSet<_>>().len();
    if unique_count != paths.len() {
      return Err("Duplicate SIMSOFT Excel files are not allowed.".to_string());
    }
    let total_max_mb = env_u64("SIMSOFT_MAX_EXCEL_TOTAL_MB", 100);
    let total_max_bytes = total_max_mb * 1024 * 1024;
    let total_size = paths.iter().try_fold(0_u64, |sum, path| {
      PathBuf::from(path)
        .metadata()
        .map(|metadata| sum.saturating_add(metadata.len()))
        .map_err(|_| "SIMSOFT Excel file does not exist.".to_string())
    })?;
    if total_size > total_max_bytes {
      return Err(format!("Selected Excel files are larger than the configured {total_max_mb} MB total limit."));
    }
    return Ok(paths);
  }
  Ok(vec![validate_excel_file_path(value_str(input, "filePath"))?])
}

pub fn validate_operator_identity(operator_identity: &Option<Value>) -> Result<(), String> {
  let Some(operator) = operator_identity else {
    return Ok(());
  };
  if !operator.is_object() {
    return Err("Invalid operator identity.".to_string());
  }
  if let Some(signed_in) = operator.get("signedIn") {
    if !signed_in.is_boolean() {
      return Err("Invalid operator identity.".to_string());
    }
  }
  for key in ["email", "tokenUserEmail"] {
    let email = value_str(operator, key);
    if !email.is_empty() && !is_safe_email(email) {
      return Err("Invalid operator identity.".to_string());
    }
  }
  let mode = value_str(operator, "authMode");
  if !mode.is_empty() && mode != "service_account" && mode != "user_oauth" {
    return Err("Invalid operator identity.".to_string());
  }
  Ok(())
}

fn operator_emails(operator_identity: &Option<Value>) -> Vec<String> {
  let Some(operator) = operator_identity else {
    return vec![];
  };
  ["email", "tokenUserEmail"]
    .iter()
    .filter_map(|key| {
      let email = value_str(operator, key).trim().to_ascii_lowercase();
      if email.is_empty() {
        None
      } else {
        Some(email)
      }
    })
    .collect()
}

pub fn require_admin(operator_identity: &Option<Value>) -> Result<(), String> {
  validate_operator_identity(operator_identity)?;
  let access = read_access_config();
  let admins: Vec<String> = value_array(&access, "adminEmails")
    .as_array()
    .cloned()
    .unwrap_or_default()
    .into_iter()
    .filter_map(|item| item.as_str().map(|email| email.trim().to_ascii_lowercase()))
    .filter(|email| is_safe_email(email))
    .collect();
  if admins.is_empty() {
    return Ok(());
  }
  let operator_emails = operator_emails(operator_identity);
  if operator_emails.iter().any(|email| admins.contains(email)) {
    Ok(())
  } else {
    Err("Admin permission is required for this action.".to_string())
  }
}

fn operator_is_admin(operator_identity: &Option<Value>, access: &Value) -> Result<bool, String> {
  validate_operator_identity(operator_identity)?;
  let admins: Vec<String> = value_array(access, "adminEmails")
    .as_array()
    .cloned()
    .unwrap_or_default()
    .into_iter()
    .filter_map(|item| item.as_str().map(|email| email.trim().to_ascii_lowercase()))
    .filter(|email| is_safe_email(email))
    .collect();
  let members: Vec<String> = value_array(access, "memberEmails")
    .as_array()
    .cloned()
    .unwrap_or_default()
    .into_iter()
    .filter_map(|item| item.as_str().map(|email| email.trim().to_ascii_lowercase()))
    .filter(|email| is_safe_email(email))
    .collect();
  let emails = operator_emails(operator_identity);
  if emails.iter().any(|email| admins.contains(email)) {
    return Ok(true);
  }
  Ok(admins.is_empty() && !emails.iter().any(|email| members.contains(email)))
}

pub fn require_branch_access(operator_identity: &Option<Value>, branch_id: &str) -> Result<(), String> {
  validate_operator_identity(operator_identity)?;
  let normalized_branch = branch_id.trim().to_ascii_uppercase();
  if !is_safe_branch_id(&normalized_branch) {
    return Err("Invalid target branch.".to_string());
  }
  let access = read_access_config();
  if operator_is_admin(operator_identity, &access)? {
    return Ok(());
  }
  let user_branches = value_object(&access, "userBranches");
  let Some(branch_map) = user_branches.as_object() else {
    return Err("This operator is not assigned to the selected branch.".to_string());
  };
  for email in operator_emails(operator_identity) {
    let assigned = branch_map.get(&email).and_then(Value::as_array).cloned().unwrap_or_default();
    if assigned.iter().any(|item| {
      let branch = item.as_str().unwrap_or_default().trim().to_ascii_uppercase();
      branch == "*" || branch == normalized_branch
    }) {
      return Ok(());
    }
  }
  Err("This operator is not assigned to the selected branch.".to_string())
}

pub fn validate_access_config(input: &Value) -> Result<(), String> {
  for key in ["adminEmails", "memberEmails"] {
    let items = value_array(input, key);
    for item in items.as_array().cloned().unwrap_or_default() {
      let email = item.as_str().unwrap_or_default();
      if !is_safe_email(email) {
        return Err("Invalid access control email.".to_string());
      }
    }
  }
  let user_branches = value_object(input, "userBranches");
  for (email, branches) in user_branches.as_object().cloned().unwrap_or_default() {
    if !is_safe_email(&email) || !branches.is_array() {
      return Err("Invalid branch access rule.".to_string());
    }
    for branch in branches.as_array().cloned().unwrap_or_default() {
      if !is_safe_branch_id(branch.as_str().unwrap_or_default()) {
        return Err("Invalid branch access rule.".to_string());
      }
    }
  }
  Ok(())
}

fn validate_branch_index(input: &Value, branch_id: &str) -> Result<(), String> {
  let branch_index = input
    .get("branchIndex")
    .and_then(Value::as_object)
    .ok_or_else(|| "Branch scan data is required.".to_string())?;
  let branch = branch_index
    .get(branch_id)
    .and_then(Value::as_object)
    .ok_or_else(|| "Folder scan required before selecting this branch.".to_string())?;
  for (candidate_id, candidate) in branch_index {
    if !is_safe_branch_id(candidate_id) || !candidate.is_object() {
      return Err("Invalid branch scan data.".to_string());
    }
    let Some(item) = candidate.as_object() else {
      return Err("Invalid branch scan data.".to_string());
    };
    let sheet_id = item.get("spreadsheet_id").and_then(Value::as_str).unwrap_or_default();
    if !is_safe_sheet_id(sheet_id) {
      return Err("Invalid branch scan data.".to_string());
    }
  }
  let sheet_id = branch.get("spreadsheet_id").and_then(Value::as_str).unwrap_or_default();
  if !is_safe_sheet_id(sheet_id) {
    return Err("Selected branch does not have a valid Google Spreadsheet ID.".to_string());
  }
  Ok(())
}

pub fn validate_operator_payload(input: &Value) -> Result<(), String> {
  let operator = input.get("operatorIdentity").cloned();
  validate_operator_identity(&operator)
}

fn validate_ibp_inputs(input: &Value) -> Result<(), String> {
  if let Some(particulars) = input.get("ibpParticulars") {
    let Some(map) = particulars.as_object() else {
      return Err("Invalid IBP particulars.".to_string());
    };
    for (key, value) in map {
      let text = value.as_str().unwrap_or_default();
      if key.len() > 128 || text.is_empty() || text.len() > 80 || text.contains('\n') || text.contains('\r') {
        return Err("Invalid IBP particulars.".to_string());
      }
    }
  }
  if let Some(breakdowns) = input.get("ibpPaymentBreakdowns") {
    let Some(map) = breakdowns.as_object() else {
      return Err("Invalid IBP payment breakdowns.".to_string());
    };
    for (key, value) in map {
      let Some(item) = value.as_object() else {
        return Err("Invalid IBP payment breakdowns.".to_string());
      };
      if key.len() > 128 {
        return Err("Invalid IBP payment breakdowns.".to_string());
      }
      for field in ["rebate", "amount", "penalty"] {
        let text = item.get(field).and_then(Value::as_str).unwrap_or_default();
        if text.len() > 32 || text.contains('\n') || text.contains('\r') {
          return Err("Invalid IBP payment breakdowns.".to_string());
        }
      }
    }
  }
  Ok(())
}

pub fn validate_google_payload(input: &mut Value, requires_file: bool, requires_confirmation: bool) -> Result<(), String> {
  if !input.is_object() {
    return Err("Posting data is required.".to_string());
  }
  validate_operator_payload(input)?;
  let folder_url = validate_google_folder_url(input.get("folderUrl").unwrap_or(&Value::Null))?;
  input["folderUrl"] = Value::String(folder_url);
  if requires_file {
    let file_paths = validate_excel_file_paths(input)?;
    input["filePath"] = Value::String(file_paths.first().cloned().unwrap_or_default());
    input["filePaths"] = Value::Array(file_paths.into_iter().map(Value::String).collect());
  }
  let branch_id = value_str(input, "branchId").trim();
  if !is_safe_branch_id(branch_id) {
    return Err("Invalid target branch.".to_string());
  }
  let operator = input.get("operatorIdentity").cloned();
  require_branch_access(&operator, branch_id)?;
  validate_branch_index(input, branch_id)?;
  if let Some(auth_mode) = input.get("authMode") {
    let mode = auth_mode.as_str().unwrap_or_default();
    if mode != "service_account" && mode != "user_oauth" {
      return Err("Invalid authentication mode.".to_string());
    }
  }
  if requires_confirmation && value_str(input, "confirmation") != "Continue Posting" {
    return Err("Final posting confirmation is required.".to_string());
  }
  if requires_confirmation && env::var("SIMSOFT_REQUIRE_USER_OAUTH_FOR_POSTING").is_ok() {
    let operator = input.get("operatorIdentity").unwrap_or(&Value::Null);
    if value_str(operator, "authMode") != "user_oauth" || !operator.get("signedIn").and_then(Value::as_bool).unwrap_or(false) {
      return Err("Google operator login is required before posting.".to_string());
    }
  }
  validate_ibp_inputs(input)
}
