# OFFICE RED PANDA

> 以 Claude Code 式 **Agent Harness（tool-use 循环）** 为内核，用 **PocketFlow** 做编排，复刻商汤「办公小浣熊」AI 智能办公助手。

模型主用 **火山引擎方舟 ARK coding plan** 的 Anthropic 兼容端点（原生 tool use），围绕「数据分析 / 文案创作 / 报告生成」打造可观测、可私有化、多租户的办公 Agent。

---

## ✨ 核心特性

- **Agent Harness 内核**：PocketFlow AgentNode 单节点自环 tool-use 循环，模型自主决策调用工具直至任务完成（`app/harness.py`）
- **数据分析工具链**：CSV/Excel 接入 → 读元信息 → 子进程/Docker 沙箱跑代码 → 生成图表 → 导出 HTML/PDF 报告
- **Plan Mode + 子代理**：人机共决策（出计划 → 审批 → 执行）、隔离上下文的子代理委派与并发调度
- **Skills + 知识库**：技能按需加载（Markdown frontmatter）、本地 embedding + 向量检索、`@触发`自动注入
- **多端前端**：Vite + React + TS + Tailwind 网页工作台（流式对话 / 上传 / 追溯 / 产物下载）
- **MCP + Hooks + 多租户**：MCP 连接器拉外部数据、Hooks 事件总线（归档/脱敏/审计）、Tenant/User/Role + 工具白名单
- **行业 Skills**：教育 / 医疗 / 电商 / 采购 / 财务 五大行业技能包，自动加载
- **可观测性**：token 统计累计、精度规范注入、`/api/metrics` 全局指标端点
- **私有化就绪**：Docker Compose 一体机部署规格 + vLLM 私有化 Provider

---

## 🧱 技术栈

| 层        | 选型                                                                 |
| --------- | -------------------------------------------------------------------- |
| 后端      | Python 3.11 · FastAPI · PocketFlow · anthropic SDK                   |
| 模型      | 火山引擎 ARK coding plan（Anthropic 兼容 `/api/coding/v1/messages`） |
| Embedding | sentence-transformers（默认 all-MiniLM-L6-v2，可切 bge-m3）          |
| 数据层    | Postgres · Redis · Qdrant · MinIO                                    |
| 前端      | Vite · React 19 · TypeScript · Tailwind CSS v4                       |
| 桌面端    | Tauri（配置就绪）                                                    |
| 沙箱      | 子进程隔离 + Docker 强隔离（daemon 不可用时降级子进程）              |

---

## 📁 目录结构

```
backend/            FastAPI + Agent（Python）
  app/
    harness.py        Agent Harness 内核（tool-use 自环循环）
    tools/            工具注册表 + 各类工具
    sandbox.py        子进程隔离代码沙箱
    dataset.py        CSV/Excel 接入 + 元数据 + parquet 落盘
    plan.py / plan_mode.py / replan.py   Plan Mode + 重跑
    subagent.py       子代理委派 + 并发调度
    context.py        上下文工程（分层提示 + 压缩 + 项目记忆）
    checkpoint.py     shared 快照 + 过程追溯
    skills.py         Skills 按需加载
    knowledge_base.py 知识库 ingestion/query
    embedding.py      本地 embedding
    at_trigger.py     @触发解析（Skill / 知识库注入）
    mcp_client.py     MCP 连接器
    hooks.py          Hooks 事件总线
    auth.py           多租户与权限
    providers.py      LLMProvider 抽象层（ark / vllm）
    main.py           FastAPI 服务层（会话/上传/SSE/追溯/产物）
  mcp_servers/        MCP 服务端示例
  run_acceptance*.py  各阶段验收脚本
  run_eval.py         Agent 评测集
frontend/           Vite + React 网页工作台
desktop/            Tauri 桌面端（构建被依赖死锁阻塞，见 desktop/README.md）
miniprogram/        小程序版（推迟）
skills/             五大行业 Skill 包（教育/医疗/电商/采购/财务）
deploy/             Docker / K8s / 私有化部署
docs/               设计文档
data/               示例数据
.venv/              本地虚拟环境（不入库）
```

---

## 🚀 快速开始

### 环境约定（重要）

- **虚拟环境**：必须用 **uv** 管理，位于 `.venv/`，禁止使用 base 环境或直接 pip 安装
- **密钥**：真实 `ARK_API_KEY` 只放本地 `.env`（已被 `.gitignore` 忽略），`.env.example` 仅放占位符，**绝不提交真实密钥**

### 1. 克隆并配置

```bash
git clone <repo-url> office_small_panda
cd office_small_panda

cp .env.example .env
# 编辑 .env，填入真实 ARK_API_KEY
```

### 2. 创建虚拟环境并装依赖

```bash
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install -e backend
```

### 3. 启动基础设施（可选，数据层服务）

```bash
docker compose up -d          # Postgres / Redis / Qdrant / MinIO + 本地 embedding
```

### 4. 启动后端

```bash
uvicorn app.main:app --reload --port 8000 --app-dir backend
```

### 5. 启动前端

```bash
cd frontend
pnpm install
pnpm dev
```

### 6. 验证 LLM 连通

```bash
.venv/bin/python -c "from app.llm import chat; print(chat([{'role':'user','content':'hi'}]).content)"
```

---

## ✅ 验收脚本

各阶段端到端验收，无需前端即可跑通：

```bash
# 阶段1：上传 CSV → Agent 自主循环 → 含图表 HTML 报告
.venv/bin/python backend/run_acceptance.py

# 阶段2：Plan → 子代理协作 → PPT
.venv/bin/python backend/run_acceptance_stage2.py

# 阶段3：上传文档 → @知识库写邮件
.venv/bin/python backend/run_acceptance_stage3.py

# 阶段6：Agent 评测集（工具准确率 / 报告可用率 / 引用真实性 / token 成本）
.venv/bin/python backend/run_eval.py
```

---

## 🔌 API 端点

| 方法 | 路径                         | 说明             |
| ---- | ---------------------------- | ---------------- |
| POST | `/api/sessions`              | 创建会话         |
| POST | `/api/sessions/{sid}/upload` | 上传数据/文档    |
| POST | `/api/sessions/{sid}/chat`   | 对话（SSE 流式） |
| GET  | `/api/sessions/{sid}/trace`  | 过程追溯         |
| GET  | `/api/sessions/{sid}/assets` | 会话产物列表     |
| GET  | `/api/files/{path}`          | 产物下载         |
| GET  | `/api/metrics`               | 全局可观测性指标 |

### Agent 工具链

`upload_data` · `read_data_meta` · `run_code` · `make_chart` · `todo` · `plan` · `export_report` · `gen_ppt` · `dispatch_subagent` · `load_skill` · `upload_doc` · `query_kb` · `call_mcp`

---

## 📈 项目进度

- [x] **阶段 0**：工程骨架 + 设计基线
- [x] **阶段 1**：Agent Harness 内核 + 数据分析工具链
- [x] **阶段 2**：Plan Mode + 子代理 + 上下文工程
- [x] **阶段 3**：Skills + 知识库 + 文案创作
- [x] **阶段 4**：多端前端（网页版 ✓ / 桌面端配置就绪阻塞 / 小程序推迟）
- [x] **阶段 5**：MCP + Hooks + 私有化 + 一体机
- [x] **阶段 6**：行业 Skills + 评测集 + token 治理 + 可观测性 + 精度规范

> 详细设计见 `办公小浣熊复刻计划报告.md`，私有化部署见 `deploy/PRIVATE_DEPLOY.md`。

---

## ⚠️ 已知欠账

- **评测集 RAG 用例 embedding 子进程加载失败**：`run_eval` 子进程跑 `rag_email` 时 sentence-transformers 仍尝试联网加载 config（huggingface.co 不可达）；手动子进程 + `HF_HUB_OFFLINE=1` 可成功，根因待查。`data_analysis` 用例不受影响。
- 性能优化（图表懒渲染、沙箱预热池、并发）待后续。
- Tauri 桌面端构建被 cookie×time 依赖死锁阻塞（阶段4遗留）。
- 沙箱强隔离需 Docker daemon 运行（阶段5降级子进程）。
