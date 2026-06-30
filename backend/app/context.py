"""上下文工程 —— 系统提示分层、长对话压缩/摘要、按需注入、项目记忆。

复刻 Claude Code 的上下文管理思想：
- 分层系统提示：基础角色 + 项目记忆 + 当前任务上下文。
- 长对话压缩：messages 累积超阈值时，用 LLM 把早期对话摘要为一条 system/user 消息，
  防止上下文膨胀与成本失控（报告 §6 风险「上下文膨胀/成本失控」对策）。
- 项目记忆：类 CLAUDE.md，持久化用户偏好与项目背景，按需注入系统提示。
- 按需注入：知识库/数据元信息等不预塞，需要时才注入（由工具产出回灌）。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .llm import chat, MODEL_LITE

# 压缩阈值：messages 条数超过此值且含较多 tool 往返时触发压缩
COMPRESS_THRESHOLD = int(os.getenv("RACCOON_COMPRESS_THRESHOLD", "20"))
# 压缩后保留的最近消息条数（近因优先）
KEEP_RECENT = int(os.getenv("RACCOON_KEEP_RECENT", "6"))

# 项目记忆文件（类 CLAUDE.md），可由用户编辑持久化偏好
MEMORY_FILE = Path(os.getenv("RACCOON_MEMORY_FILE", "CLAUDE.md"))


def load_project_memory() -> str:
    """读取项目记忆文件内容（不存在则空）。"""
    if MEMORY_FILE.exists():
        return MEMORY_FILE.read_text(encoding="utf-8")
    return ""


def build_system(base: str, *, memory: str | None = None, extra: str = "") -> str:
    """分层组装系统提示：base 角色 + 项目记忆 + 额外上下文。"""
    parts = [base]
    mem = memory if memory is not None else load_project_memory()
    if mem.strip():
        parts.append(f"\n\n【项目记忆】\n{mem.strip()}")
    if extra.strip():
        parts.append(f"\n\n【当前任务上下文】\n{extra.strip()}")
    return "".join(parts)


async def _compress_async(messages: list[dict]) -> str:
    """异步摘要早期对话。这里用同步 chat 包一层（阶段2 先用同步）。"""
    return _compress(messages)


def _compress(messages: list[dict]) -> str:
    """把一段 messages 摘要为简短文本。"""
    # 提取文本与工具调用要点
    lines = []
    for m in messages:
        role = m.get("role", "?")
        content = m.get("content")
        if isinstance(content, str):
            lines.append(f"[{role}] {content[:500]}")
        elif isinstance(content, list):
            for block in content:
                btype = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
                if btype == "text":
                    txt = block.get("text") if isinstance(block, dict) else getattr(block, "text", "")
                    lines.append(f"[{role}] {txt[:300]}")
                elif btype == "tool_use":
                    name = block.get("name") if isinstance(block, dict) else getattr(block, "name", "")
                    lines.append(f"[{role}→工具] {name}")
                elif btype == "tool_result":
                    c = block.get("content") if isinstance(block, dict) else getattr(block, "content", "")
                    lines.append(f"[{role}←结果] {str(c)[:200]}")
    transcript = "\n".join(lines)[:8000]
    summary_resp = chat(
        model=MODEL_LITE,
        max_tokens=600,
        system="你是上下文压缩器。把对话历史压缩为简洁摘要：保留关键事实、已得结论、未决事项，丢弃冗余工具细节。用中文要点输出。",
        messages=[{"role": "user", "content": f"请压缩以下对话历史：\n\n{transcript}"}],
    )
    out = []
    for b in summary_resp.content:
        if getattr(b, "type", None) == "text":
            out.append(b.text)
    return "\n".join(out) or "(无摘要)"


def maybe_compress(messages: list[dict]) -> tuple[list[dict], bool]:
    """若 messages 超阈值，压缩早期部分，返回 (新 messages, 是否压缩)。

    策略：保留最近 KEEP_RECENT 条；其前的部分压缩为一条 user 消息置于开头。
    """
    if len(messages) <= COMPRESS_THRESHOLD:
        return messages, False
    old = messages[:-KEEP_RECENT]
    recent = messages[-KEEP_RECENT:]
    summary = _compress(old)
    compressed = [{"role": "user", "content": f"【前期对话摘要】\n{summary}"}] + recent
    return compressed, True
