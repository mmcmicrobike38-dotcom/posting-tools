use std::{fs, io::Write, panic};

use super::config::{now_timestamp, runtime_log_dir};

pub fn append_runtime_log(file_name: &str, message: &str) {
  let log_dir = runtime_log_dir();
  let _ = fs::create_dir_all(&log_dir);
  let path = log_dir.join(file_name);
  let line = format!("{} {}\n", now_timestamp(), message);
  if let Ok(mut file) = fs::OpenOptions::new().create(true).append(true).open(path) {
    let _ = file.write_all(line.as_bytes());
  }
}

pub fn install_panic_hook() {
  panic::set_hook(Box::new(|panic_info| {
    append_runtime_log("desktop_crash.log", &format!("panic: {panic_info}"));
  }));
}
