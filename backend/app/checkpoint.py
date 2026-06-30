"""shared 状态快照 + 过程追溯 —— 自建 checkpointing（PocketFlow 不给，见报告 §2.4 代价1/3）。

设计：
- CheckpointStore：每步把 shared 的可序列化部分快照落盘（JSON），支持回看与分支重跑。
- 追溯记录增强：除工具调用外，记录每步的 assistant 文本/思考摘要、模型调用元信息。
- shared 中不可序列化的对象（ToolRegistry、DataFrame）在快照时跳过或转可序列化形式。

快照可用于：
  1. 可追溯：任意一步的 shared 状态可回看。
  2. 分支重跑：从某步快照重建 shared，修改后重跑（Plan Mode replan / 实验不同路径）。
  3. 持久化恢复：长任务跨进程恢复（阶段5 持久化执行器的基础）。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from .dataset import WORKDIR

CHECKPOINT_DIR = Path(os.getenv("RACCOON_CHECKPOINT_DIR", WORKDIR / "checkpoints"))

# shared 中这些键不可序列化或体积大，快照时跳过（工具注册表等）
_SKIP_KEYS = {"tools"}


def _safe(obj: Any) -> Any:
    """把对象转为可 JSON 序列化形式，跳过不可序列化的。"""
    try:
        json.dumps(obj, ensure_ascii=False, default=str)
        return obj
    except (TypeError, ValueError):
        return f"<{type(obj).__name__}>"


class CheckpointStore:
    """按会话 id 管理快照。"""

    def __init__(self, session_id: str | None = None) -> None:
        self.session_id = session_id or f"sess_{int(time.time())}"
        self.dir = CHECKPOINT_DIR / self.session_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.steps: list[dict] = []

    def snapshot(self, shared: dict, *, step: int, action: str, note: str = "") -> dict:
        """记录一步快照，返回快照元信息。"""
        safe_shared = {k: _safe(v) for k, v in shared.items() if k not in _SKIP_KEYS}
        snap = {
            "step": step,
            "action": action,
            "note": note,
            "timestamp": time.time(),
            "shared": safe_shared,
        }
        self.steps.append(snap)
        path = self.dir / f"step_{step:03d}_{action}.json"
        path.write_text(json.dumps(snap, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return {"step": step, "action": action, "path": str(path)}

    def load(self, step: int) -> dict | None:
        """加载某步快照（用于分支重跑）。"""
        for p in self.dir.glob(f"step_{step:03d}_*.json"):
            return json.loads(p.read_text(encoding="utf-8"))
        return None

    def summary(self) -> list[dict]:
        """追溯摘要：每步的 step/action/note。"""
        return [{"step": s["step"], "action": s["action"], "note": s["note"]} for s in self.steps]
