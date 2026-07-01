# 桌面端（Tauri 封装网页版）

封装 `frontend/` 网页版为桌面应用，复用前端构建产物。

## 构建

前置：
- Rust 工具链（`rustup default stable`），建议配国内镜像加速：
  ```sh
  export RUSTUP_DIST_SERVER=https://mirrors.ustc.edu.cn/rust-static
  export RUSTUP_UPDATE_ROOT=https://mirrors.ustc.edu.cn/rust-static/rustup
  ```
- cargo 镜像（`~/.cargo/config.toml`）：
  ```toml
  [source.crates-io]
  replace-with = "ustc"
  [source.ustc]
  registry = "sparse+https://mirrors.ustc.edu.cn/crates.io-index/"
  ```

构建：
```sh
cd desktop/src-tauri
cargo tauri build      # 或 cargo build
```

dev 模式（需 frontend dev server + 后端 FastAPI 同时运行）：
```sh
cd frontend && pnpm dev          # :5173
cd backend && uvicorn app.main:app --port 8000 --app-dir backend
cd desktop/src-tauri && cargo tauri dev
```

## 已知阻塞（如实记录）

Tauri 2.11.x 依赖 `cookie 0.18.1`，其代码与 `time ≥0.3.41` 不兼容
（`FormatItem::parse` 在 time 0.3.41 改为 2 参）；而 tauri 2.11 间接依赖
`plist 1.9` / `tauri-utils 2.9` 强制 `time ≥0.3.47`，形成依赖死锁。

这是 Rust 生态依赖摩擦，非项目架构问题。Tauri 配置已完整就绪
（tauri.conf.json / Cargo.toml / main.rs / build.rs），
待 tauri 生态更新 cookie 或 time 兼容后 `cargo tauri build` 即可构建。

临时绕过思路（未采用）：`[patch.crates-io]` 替换 cookie 为修复 fork。
