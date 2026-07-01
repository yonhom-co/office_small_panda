"""FastAPI 服务层 —— 把阶段1-3 的 Agent 能力 HTTP 化。

端点：
- POST /api/sessions               创建会话
- POST /api/sessions/{id}/upload   上传数据(CSV/Excel)或文档(PDF/Word/TXT)入库/知识库
- POST /api/sessions/{id}/chat     SSE 流式对话（对接 harness stream + on_event）
- GET  /api/sessions/{id}/trace    查看工具调用追溯
- GET  /api/sessions/{id}/assets   列出报告/PPT 等产物
- GET  /api/files/{path}           下载产物文件

会话存内存（阶段5 持久化）。SSE 推送 text 增量、工具调用事件、完成事件。
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from .dataset import ingest, WORKDIR
from .knowledge_base import ingest_document
from .harness import build_flow, SYSTEM_PROMPT
from .context import build_system
from .checkpoint import CheckpointStore
import app.tools_registry  # noqa: F401  触发工具注册

app = FastAPI(title="办公小浣熊 Raccoon API", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# 会话存储（内存；阶段5 持久化）
_sessions: dict[str, dict] = {}


class ChatRequest(BaseModel):
    message: str
    max_steps: int = 20


@app.post("/api/sessions")
def create_session(user_id: str = "analyst1") -> dict:
    # user_id 作为查询参数 ?user_id=admin1；默认 analyst1
    from .hooks import default_bus
    from .auth import get_user, tenant_scope, filtered_tools
    from . import tools_registry
    user = get_user(user_id) or get_user("analyst1")
    sid = uuid.uuid4().hex[:12]
    ckpt = CheckpointStore()
    shared = {
        "messages": [],
        "max_steps": 20,
        "checkpoint": ckpt,
        "hooks": default_bus,
        "system": SYSTEM_PROMPT,
    }
    tenant_scope(shared, user)
    shared["tools"] = filtered_tools(user, tools_registry.default_registry)
    _sessions[sid] = {"shared": shared, "ckpt": ckpt, "user": user}
    return {"session_id": sid, "user": user.uid, "tenant": user.tenant, "role": user.role}


def _get(sid: str) -> dict:
    if sid not in _sessions:
        raise HTTPException(404, f"会话 {sid} 不存在")
    return _sessions[sid]


@app.post("/api/sessions/{sid}/upload")
async def upload(sid: str, file: UploadFile = File(...), kb: str | None = None) -> dict:
    sess = _get(sid)
    shared = sess["shared"]
    # 落盘上传文件
    upload_dir = WORKDIR / "uploads" / sid
    upload_dir.mkdir(parents=True, exist_ok=True)
    dst = upload_dir / file.filename
    dst.write_bytes(await file.read())

    suffix = dst.suffix.lower()
    if suffix in (".csv", ".xlsx", ".xls"):
        meta = ingest(str(dst), shared)
        return {"kind": "dataset", "name": meta["name"], "rows": meta["rows"], "cols": meta["cols"]}
    # 文档 → 知识库
    kb_name = kb or "default"
    info = ingest_document(str(dst), kb=kb_name)
    shared.setdefault("kb_list", [])
    if kb_name not in shared["kb_list"]:
        shared["kb_list"].append(kb_name)
    return {"kind": "document", "kb": kb_name, "chunks": info["chunks"], "chars": info["chars"]}


@app.post("/api/sessions/{sid}/chat")
def chat(sid: str, req: ChatRequest):
    sess = _get(sid)
    shared = sess["shared"]
    shared["max_steps"] = req.max_steps
    shared["messages"].append({"role": "user", "content": req.message})

    def event_stream():
        queue: list[str] = []

        def on_text(chunk: str):
            queue.append(json.dumps({"type": "text", "delta": chunk}, ensure_ascii=False))

        def on_event(ev: dict):
            queue.append(json.dumps({"type": ev.get("type"), "data": ev}, ensure_ascii=False))

        shared["stream"] = True
        shared["on_text"] = on_text
        shared["on_event"] = on_event

        # 在子线程跑 harness，主线程流式吐 queue
        import threading

        done = threading.Event()

        def run():
            try:
                flow = build_flow()
                flow.run(shared)
            except Exception as e:
                on_event({"type": "error", "message": f"{type(e).__name__}: {e}"})
            finally:
                done.set()

        t = threading.Thread(target=run, daemon=True)
        t.start()
        while not done.is_set() or queue:
            while queue:
                yield f"data: {queue.pop(0)}\n\n"
            if not done.is_set():
                # 短暂等待让生产者填充
                import time
                time.sleep(0.01)
        # 收尾
        yield f"data: {json.dumps({'type': 'done', 'result': shared.get('result','')[:2000]}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/sessions/{sid}/trace")
def trace(sid: str) -> dict:
    shared = _get(sid)["shared"]
    return {
        "trace": shared.get("trace", []),
        "todos": shared.get("todos", []),
        "kb_used": shared.get("kb_used", []),
        "loaded_skills": shared.get("loaded_skills", []),
        "token_stats": shared.get("token_stats", {}),
        "compress_count": shared.get("compress_count", 0),
        "report_path": shared.get("report_path"),
        "report_pdf_path": shared.get("report_pdf_path"),
        "ppt_path": shared.get("ppt_path"),
    }


@app.get("/api/metrics")
def metrics() -> dict:
    """全局可观测性：会话/token/压缩/工具调用/hooks 审计（阶段6 步骤6）。"""
    from .hooks import AUDIT_LOG
    sessions = []
    total_tokens = {"input": 0, "output": 0, "calls": 0}
    total_compress = 0
    tool_counts: dict[str, int] = {}
    for sid, sess in _sessions.items():
        shared = sess["shared"]
        ts = shared.get("token_stats", {})
        total_tokens["input"] += ts.get("input", 0)
        total_tokens["output"] += ts.get("output", 0)
        total_tokens["calls"] += ts.get("calls", 0)
        total_compress += shared.get("compress_count", 0)
        for t in shared.get("trace", []):
            name = t.get("name", "")
            if name not in ("end_turn", "max_steps_reached", "aborted",
                            "context_compressed", "at_trigger"):
                tool_counts[name] = tool_counts.get(name, 0) + 1
        sessions.append({"sid": sid, "user": sess["user"].uid,
                         "tenant": sess["user"].tenant, "role": sess["user"].role,
                         "tokens": ts, "steps": shared.get("step", 0),
                         "done": bool(shared.get("result"))})
    audit_lines = 0
    if AUDIT_LOG.exists():
        audit_lines = sum(1 for _ in AUDIT_LOG.open(encoding="utf-8"))
    return {
        "sessions": len(_sessions),
        "total_tokens": total_tokens,
        "compress_count": total_compress,
        "tool_calls": tool_counts,
        "audit_log_lines": audit_lines,
        "sessions_detail": sessions,
    }


@app.get("/api/sessions/{sid}/assets")
def assets(sid: str) -> dict:
    shared = _get(sid)["shared"]
    items = []
    for key in ("report_path", "report_pdf_path", "ppt_path"):
        p = shared.get(key)
        if p:
            items.append({"kind": key, "path": p})
    return {"assets": items}


@app.get("/api/files/{path:path}")
def get_file(path: str):
    p = Path(path)
    if not p.exists() or not p.is_absolute():
        raise HTTPException(404, "文件不存在")
    if not str(p).startswith(str(WORKDIR)):
        raise HTTPException(403, "仅允许访问工作目录文件")
    return FileResponse(str(p), filename=p.name)
