"""Hooks 引擎 —— 事件总线 + 规则引擎（补齐阶段5 步骤2）。

把"每次 X 就 Y"的固定逻辑从模型剥离到外壳，可靠可审计：
- 报告生成后自动归档
- 敏感数据自动脱敏
- 超时自动中止
- 每次工具调用写审计日志

设计：事件总线（emit/listen），harness 在节点 post 与工具执行点 emit 事件；
规则引擎匹配事件触发动作（确定性，不依赖模型）。规则可热插拔。
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .dataset import WORKDIR

AUDIT_LOG = Path(WORKDIR) / "audit.log"
ARCHIVE_DIR = Path(WORKDIR) / "archive"


@dataclass
class Event:
    type: str                 # 事件类型，如 tool_call / report_generated / step
    data: dict = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


# 敏感数据脱敏规则（正则 → 替换）
SENSITIVE_PATTERNS = [
    (re.compile(r"\b1[3-9]\d{9}\b"), "[手机号]"),                # 手机号
    (re.compile(r"\b\d{15}|\d{18}[0-9Xx]\b"), "[身份证]"),        # 身份证
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[邮箱]"),      # 邮箱
    (re.compile(r"\b621\d{15,16}\b"), "[银行卡]"),               # 银行卡(示例前缀)
]


def mask_sensitive(text: str) -> str:
    """脱敏：手机号/身份证/邮箱/银行卡 → 占位。"""
    if not text:
        return text
    for pat, repl in SENSITIVE_PATTERNS:
        text = pat.sub(repl, text)
    return text


class EventBus:
    """事件总线 + 规则引擎。"""

    def __init__(self) -> None:
        self._rules: list[tuple[str, Callable[[Event], None]]] = []
        self._audit: list[dict] = []

    def on(self, event_type: str, action: Callable[[Event], None]) -> None:
        """注册规则：匹配 event_type 触发 action。event_type 可用 '*' 匹配全部。"""
        self._rules.append((event_type, action))

    def emit(self, event: Event) -> None:
        """触发事件，执行所有匹配规则。规则异常不击垮主流程。"""
        for etype, action in self._rules:
            if etype == "*" or etype == event.type:
                try:
                    action(event)
                except Exception as e:  # noqa: BLE001
                    self._audit.append({"ts": event.ts, "hook_error": str(e),
                                        "event": event.type})

    def audit(self) -> list[dict]:
        return list(self._audit)


def _archive_report(event: Event) -> None:
    """报告生成后归档。"""
    path = event.data.get("path")
    if not path:
        return
    src = Path(path)
    if not src.exists():
        return
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    dst = ARCHIVE_DIR / f"{int(time.time())}_{src.name}"
    dst.write_bytes(src.read_bytes())


def _audit_tool_call(event: Event) -> None:
    """工具调用写审计日志。"""
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": event.ts, "type": event.type, **event.data}
    # 脱敏后写日志
    safe = mask_sensitive(json.dumps(entry, ensure_ascii=False, default=str))
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(safe + "\n")


def _mask_in_output(event: Event) -> None:
    """对工具输出做脱敏（在 data 上原地改，便于回灌前清洗）。"""
    out = event.data.get("output")
    if isinstance(out, str):
        event.data["output"] = mask_sensitive(out)


def build_default_bus() -> EventBus:
    """构建默认 Hooks：归档/脱敏/审计。"""
    bus = EventBus()
    bus.on("report_generated", _archive_report)
    bus.on("tool_call", _mask_in_output)
    bus.on("tool_call", _audit_tool_call)
    bus.on("tool_result", _audit_tool_call)
    return bus


# 全局默认总线
default_bus = build_default_bus()
