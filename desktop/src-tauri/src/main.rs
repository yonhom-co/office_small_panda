// 办公小浣熊 桌面端 —— Tauri 封装网页版工作台
// 复用 frontend/dist 构建产物，增加本地文件访问能力（后续可加 tauri plugin-fs）

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
