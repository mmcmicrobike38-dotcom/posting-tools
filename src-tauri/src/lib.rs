mod api;
mod infrastructure;

pub fn run() {
  infrastructure::logging::install_panic_hook();
  tauri::Builder::default()
    .plugin(tauri_plugin_dialog::init())
    .plugin(tauri_plugin_opener::init())
    .invoke_handler(tauri::generate_handler![
      api::commands::shell_status,
      api::commands::app_get_status,
      api::commands::app_request_access,
      api::commands::app_save_access_config,
      api::commands::app_open_google_test_users_page,
      api::commands::app_open_support_folder,
      api::commands::app_health_check,
      api::commands::dialog_choose_simsoft_file,
      api::commands::dialog_choose_simsoft_files,
      api::commands::simsoft_parse_file,
      api::commands::simsoft_parse_files,
      api::commands::google_scan_folder,
      api::commands::google_build_previews,
      api::commands::google_get_sheet_stats,
      api::commands::google_post_previews,
      api::commands::operator_get_identity,
      api::commands::operator_login_google,
      api::commands::operator_logout_google,
      api::commands::duplicates_get_status,
      api::commands::duplicates_reset,
      api::commands::cache_clear
    ])
    .run(tauri::generate_context!())
    .expect("failed to run SIMSOFT Tauri shell");
}
