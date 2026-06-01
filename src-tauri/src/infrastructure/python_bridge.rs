use serde::Deserialize;
use serde_json::{json, Value};
use std::{
  env,
  io::{BufRead, BufReader, Read, Write},
  path::{Path, PathBuf},
  process::{Child, ChildStdin, Command, Stdio},
  sync::{mpsc::{self, Receiver}, Mutex, OnceLock},
  thread,
  time::{Duration, Instant},
};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

use super::config::{
  auth_mode, config_path, data_path, path_string, runtime_log_dir_string, runtime_oauth_token_dir, workspace_root,
};

#[derive(Deserialize)]
struct BridgeResponse {
  ok: bool,
  result: Option<Value>,
  error: Option<String>,
}

struct BridgeSidecar {
  child: Child,
  stdin: ChildStdin,
  stdout_lines: Receiver<Result<String, String>>,
}

static BRIDGE_SIDECAR: OnceLock<Mutex<Option<BridgeSidecar>>> = OnceLock::new();

fn command_name(payload: &Value) -> &str {
  payload.get("command").and_then(Value::as_str).unwrap_or("unknown")
}

fn timeout_for_command(command: &str) -> Duration {
  if let Ok(value) = env::var("SIMSOFT_PYTHON_BRIDGE_TIMEOUT_MS") {
    if let Ok(ms) = value.parse::<u64>() {
      if ms > 0 {
        return Duration::from_millis(ms);
      }
    }
  }
  let seconds = match command {
    "scan_google_folder" => 180,
    "build_google_previews" => 240,
    "post_google_previews" => 300,
    "google_sheet_stats" => 120,
    "operator_login_google" => 240,
    "parse_simsoft" => 120,
    _ => 60,
  };
  Duration::from_secs(seconds)
}

fn timeout_message(command: &str) -> String {
  format!("Python worker timed out while running {command}. The worker was restarted. Please try the action again.")
}

pub fn python_executable() -> String {
  let local = workspace_root().join(".venv").join("Scripts").join("python.exe");
  if local.exists() {
    path_string(local)
  } else {
    "python".to_string()
  }
}

pub fn packaged_bridge_executable() -> Option<PathBuf> {
  if cfg!(debug_assertions) && workspace_root().join("scripts").join("python_bridge.py").exists() {
    return None;
  }
  if let Ok(value) = env::var("SIMSOFT_PYTHON_BRIDGE_EXE") {
    let path = PathBuf::from(value);
    if path.exists() {
      return Some(path);
    }
  }
  let root = workspace_root();
  let exe_dir = env::current_exe()
    .ok()
    .and_then(|path| path.parent().map(Path::to_path_buf))
    .unwrap_or_else(|| root.clone());
  let candidates = [
    root.join("dist-python").join("simsoft-python-bridge").join("simsoft-python-bridge.exe"),
    root.join("_up_").join("dist-python").join("simsoft-python-bridge").join("simsoft-python-bridge.exe"),
    root.join("python_bridge").join("simsoft-python-bridge.exe"),
    exe_dir.join("dist-python").join("simsoft-python-bridge").join("simsoft-python-bridge.exe"),
    exe_dir.join("_up_").join("dist-python").join("simsoft-python-bridge").join("simsoft-python-bridge.exe"),
    exe_dir.join("resources").join("dist-python").join("simsoft-python-bridge").join("simsoft-python-bridge.exe"),
    exe_dir.join("resources").join("_up_").join("dist-python").join("simsoft-python-bridge").join("simsoft-python-bridge.exe"),
    exe_dir.join("resources").join("python_bridge").join("simsoft-python-bridge.exe"),
  ];
  candidates.into_iter().find(|path| path.exists())
}

fn bridge_command(server_mode: bool) -> Command {
  let root = workspace_root();
  let script_candidates = [
    root.join("scripts").join("python_bridge.py"),
    root.join("_up_").join("scripts").join("python_bridge.py"),
    root.join("resources").join("scripts").join("python_bridge.py"),
    root.join("resources").join("_up_").join("scripts").join("python_bridge.py"),
  ];
  let script = script_candidates
    .into_iter()
    .find(|path| path.exists())
    .unwrap_or_else(|| root.join("scripts").join("python_bridge.py"));
  let bridge_exe = packaged_bridge_executable();
  let mut command_builder = if let Some(path) = bridge_exe {
    Command::new(path)
  } else {
    let mut command = Command::new(python_executable());
    command.arg(script);
    command
  };
  if server_mode {
    command_builder.arg("--server");
  }
  #[cfg(windows)]
  command_builder.creation_flags(0x08000000);
  let duplicate_history_path = PathBuf::from(data_path("duplicate_history.csv"));
  let cache_db_path = duplicate_history_path
    .parent()
    .unwrap_or_else(|| Path::new("data"))
    .join("cache")
    .join("simsoft_cache.sqlite");
  command_builder
    .current_dir(&root)
    .env("SIMSOFT_SERVICE_ACCOUNT_JSON_PATH", config_path("service_account.json"))
    .env("SIMSOFT_OAUTH_CLIENT_JSON_PATH", config_path("oauth_client.json"))
    .env("SIMSOFT_OAUTH_TOKEN_DIR", runtime_oauth_token_dir())
    .env("SIMSOFT_DUPLICATE_HISTORY_PATH", data_path("duplicate_history.csv"))
    .env("SIMSOFT_POSTED_BATCHES_PATH", data_path("posted_batches.csv"))
    .env("SIMSOFT_POSTING_LOCKS_PATH", data_path("posting_locks.json"))
    .env("SIMSOFT_CACHE_DB_PATH", path_string(cache_db_path))
    .env("SIMSOFT_LOG_DIR", runtime_log_dir_string());
  command_builder
}

fn bridge_payload(command: &str, mut payload: Value) -> Value {
  if !payload.is_object() {
    payload = json!({});
  }
  payload["command"] = Value::String(command.to_string());
  payload
}

fn parse_bridge_response(raw: &str, stderr: &str) -> Result<Value, String> {
  let parsed: BridgeResponse = serde_json::from_str(raw.trim())
    .or_else(|_| {
      raw
        .rfind("{\"ok\"")
        .ok_or_else(|| serde_json::Error::io(std::io::Error::new(std::io::ErrorKind::InvalidData, "missing bridge JSON")))
        .and_then(|start| serde_json::from_str(&raw[start..]))
    })
    .map_err(|_| format!("Python bridge returned invalid JSON. {stderr}"))?;
  if parsed.ok {
    Ok(parsed.result.unwrap_or(Value::Null))
  } else {
    Err(parsed.error.unwrap_or_else(|| stderr.to_string()))
  }
}

fn start_sidecar() -> Result<BridgeSidecar, String> {
  let mut child = bridge_command(true)
    .stdin(Stdio::piped())
    .stdout(Stdio::piped())
    .stderr(Stdio::null())
    .spawn()
    .map_err(|error| format!("Python bridge sidecar could not start: {error}"))?;
  let stdin = child.stdin.take().ok_or_else(|| "Python bridge sidecar stdin is unavailable.".to_string())?;
  let stdout = child.stdout.take().ok_or_else(|| "Python bridge sidecar stdout is unavailable.".to_string())?;
  let (sender, receiver) = mpsc::channel();
  thread::spawn(move || {
    let mut reader = BufReader::new(stdout);
    loop {
      let mut line = String::new();
      match reader.read_line(&mut line) {
        Ok(0) => break,
        Ok(_) => {
          if sender.send(Ok(line)).is_err() {
            break;
          }
        }
        Err(error) => {
          let _ = sender.send(Err(error.to_string()));
          break;
        }
      }
    }
  });
  Ok(BridgeSidecar {
    child,
    stdin,
    stdout_lines: receiver,
  })
}

fn sidecar_payload(payload: Value) -> Result<Value, String> {
  let command = command_name(&payload).to_string();
  let timeout = timeout_for_command(&command);
  let store = BRIDGE_SIDECAR.get_or_init(|| Mutex::new(None));
  let mut guard = store.lock().map_err(|_| "Python bridge sidecar lock failed.".to_string())?;
  if guard.as_mut().and_then(|sidecar| sidecar.child.try_wait().ok()).flatten().is_some() {
    *guard = None;
  }
  if guard.is_none() {
    *guard = Some(start_sidecar()?);
  }
  let sidecar = guard.as_mut().ok_or_else(|| "Python bridge sidecar is unavailable.".to_string())?;
  let body = payload.to_string();
  let input_result = sidecar
    .stdin
    .write_all(body.as_bytes())
    .and_then(|_| sidecar.stdin.write_all(b"\n"))
    .and_then(|_| sidecar.stdin.flush());
  if let Err(error) = input_result {
    *guard = None;
    return Err(format!("Python bridge sidecar input failed: {error}"));
  }

  let line = match sidecar.stdout_lines.recv_timeout(timeout) {
    Ok(Ok(line)) => line,
    Ok(Err(error)) => {
      *guard = None;
      return Err(format!("Python bridge sidecar output failed: {error}"));
    }
    Err(mpsc::RecvTimeoutError::Timeout) => {
      let _ = sidecar.child.kill();
      let _ = sidecar.child.wait();
      *guard = None;
      return Err(timeout_message(&command));
    }
    Err(mpsc::RecvTimeoutError::Disconnected) => {
      *guard = None;
      return Err("Python bridge sidecar stopped unexpectedly.".to_string());
    }
  };
  parse_bridge_response(&line, "")
}

fn one_shot_payload(payload: Value) -> Result<Value, String> {
  let command = command_name(&payload).to_string();
  let timeout = timeout_for_command(&command);
  let mut child = bridge_command(false)
    .stdin(Stdio::piped())
    .stdout(Stdio::piped())
    .stderr(Stdio::piped())
    .spawn()
    .map_err(|error| format!("Python bridge could not start: {error}"))?;

  let mut stdout = child.stdout.take().ok_or_else(|| "Python bridge stdout is unavailable.".to_string())?;
  let mut stderr = child.stderr.take().ok_or_else(|| "Python bridge stderr is unavailable.".to_string())?;
  let stdout_reader = thread::spawn(move || {
    let mut text = String::new();
    let _ = stdout.read_to_string(&mut text);
    text
  });
  let stderr_reader = thread::spawn(move || {
    let mut text = String::new();
    let _ = stderr.read_to_string(&mut text);
    text
  });

  if let Some(stdin) = child.stdin.as_mut() {
    stdin
      .write_all(payload.to_string().as_bytes())
      .map_err(|error| format!("Python bridge input failed: {error}"))?;
  }
  drop(child.stdin.take());

  let started = Instant::now();
  loop {
    if child
      .try_wait()
      .map_err(|error| format!("Python bridge failed: {error}"))?
      .is_some()
    {
      break;
    }
    if started.elapsed() > timeout {
      let _ = child.kill();
      let _ = child.wait();
      return Err(timeout_message(&command));
    }
    thread::sleep(Duration::from_millis(50));
  }
  let stdout = stdout_reader.join().unwrap_or_default();
  let stderr = stderr_reader.join().unwrap_or_default();
  parse_bridge_response(&stdout, &stderr)
}

pub fn python_bridge_payload(command: &str, payload: Value) -> Result<Value, String> {
  let payload = bridge_payload(command, payload);
  if env::var("SIMSOFT_DISABLE_PYTHON_SIDECAR").is_ok() {
    return one_shot_payload(payload);
  }
  match sidecar_payload(payload.clone()) {
    Ok(result) => Ok(result),
    Err(sidecar_error) => {
      if let Some(store) = BRIDGE_SIDECAR.get() {
        if let Ok(mut guard) = store.lock() {
          *guard = None;
        }
      }
      if sidecar_error.contains("timed out") {
        return Err(sidecar_error);
      }
      one_shot_payload(payload).map_err(|fallback_error| {
        format!("Python bridge sidecar failed: {sidecar_error}. One-shot fallback failed: {fallback_error}")
      })
    }
  }
}

pub fn restart_python_sidecar() {
  if let Some(store) = BRIDGE_SIDECAR.get() {
    if let Ok(mut guard) = store.lock() {
      if let Some(mut sidecar) = guard.take() {
        let _ = sidecar.child.kill();
        let _ = sidecar.child.wait();
      }
    }
  }
}

pub fn fallback_operator(error: Option<String>) -> Value {
  json!({
    "email": "",
    "name": "",
    "signedIn": false,
    "tokenUserEmail": "",
    "authMode": auth_mode(),
    "error": error.unwrap_or_default()
  })
}
