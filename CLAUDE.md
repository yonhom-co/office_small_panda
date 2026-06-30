# 办公小浣熊 Raccoon 复刻项目

## 项目简介
复刻商汤「办公小浣熊」的 AI 智能办公助手。以 Claude Code 式 **Agent Harness（tool-use 循环）** 为内核，用 **PocketFlow** 做编排，模型主用 **火山引擎方舟 ARK coding plan 的 Anthropic 兼容端点**（原生 tool use）。

详见 `办公小浣熊复刻计划报告.md`。

## 技术栈
- 后端：Python 3.11 + FastAPI + PocketFlow + anthropic SDK
- 虚拟环境：**uv**（必须用 uv，不污染 base，不用 pip 直接装）
- 模型：火山引擎 ARK coding plan（Anthropic 兼容 `/api/coding/v1/messages`）
- 数据层：Postgres / Redis / Qdrant / MinIO
- 前端：Next.js（后续阶段）

## 环境约定（重要）
- **虚拟环境**：用 `uv` 管理，虚拟环境位于 `.venv/`。禁止使用 base 环境或直接 pip 安装。
  - 创建：`uv venv --python 3.11 .venv`
  - 装包：`uv pip install <pkg>` 或 `uv add <pkg>`
  - 运行：`.venv/bin/python ...`
- **密钥**：真实 `ARK_API_KEY` 只在本地 `.env`（已被 `.gitignore` 忽略）。`.env.example` 仅放占位符。**绝不提交真实密钥。**

## 目录结构
```
backend/      FastAPI + Agent（Python）
frontend/     Next.js 网页版（后续）
desktop/      Tauri 桌面端（后续）
miniprogram/  小程序版（后续）
deploy/       Docker / K8s / 私有化
docs/         设计文档
.venv/        本地虚拟环境（不入库）
```

## 常用命令
```bash
# 后端开发
source .venv/bin/activate
uv pip install -e backend
uvicorn app.main:app --reload --app-dir backend

# 基础设施
docker compose up -d

# 验证 LLM 连通
.venv/bin/python -c "from app.llm import chat; print(chat([{'role':'user','content':'hi'}]).content)"
```

## 当前进度
- [x] 阶段 0：工程骨架 + 设计基线
- [x] 阶段 1：Agent Harness 内核 + 数据分析工具链
- [ ] 阶段 2：Plan Mode + 子代理 + 上下文工程
- [ ] 阶段 3：Skills + 知识库 + 文案创作
- [ ] 阶段 4：多端前端
- [ ] 阶段 5：MCP + Hooks + 私有化 + 一体机
- [ ] 阶段 6：优化与行业场景

## 阶段 1 产物
- `app/harness.py`：PocketFlow AgentNode 单节点自环 tool-use 循环（核心内核）
- `app/tools/`：工具注册表 + read_data_meta / run_code / make_chart / todo / export_report
- `app/sandbox.py`：子进程隔离代码沙箱（预加载 pandas/sklearn/matplotlib/plotly，savefig 劫持收集图表）
- `app/dataset.py`：CSV/Excel 接入 + 元数据 + parquet 落盘
- `backend/run_acceptance.py`：端到端验收脚本

验收：`uv run python backend/run_acceptance.py`（上传 sample_sales.csv → Agent 自主循环 → 含图表 HTML 报告）
