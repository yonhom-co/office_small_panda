"""@触发解析 —— 对话中 @名称 自动触发 Skill 载入或知识库检索注入。

规则：
- @writing / @某能力 → 载入对应 Skill 指令到系统提示
- @知识库名（非 Skill） → 对该知识库做语义检索（基于用户消息内容），
  把检索到的片段注入系统提示，供 Agent 引用

这样用户输入"基于 @公司介绍 写一封商务合作邮件"会被自动解析：
公司介绍 不是 Skill → 当作知识库名检索，相关片段注入上下文。
"""
from __future__ import annotations

import re

from .skills import default_skills
from .knowledge_base import query_kb, default_store


_AT_PATTERN = re.compile(r"@([\w一-龥-]+)")


def parse_at_mentions(text: str) -> list[str]:
    """提取消息中所有 @名称。"""
    return _AT_PATTERN.findall(text or "")


def resolve_mentions(user_text: str, shared: dict) -> str:
    """解析 @触发，返回需注入系统提示的文本。

    - 是 Skill 名 → 载入 Skill 指令
    - 否则视为知识库名 → 检索并把片段注入
    返回注入文本（空串表示无需注入）。
    """
    names = parse_at_mentions(user_text)
    if not names:
        return ""

    injections = []
    for name in names:
        if default_skills.get(name):
            # Skill 触发
            prompt = default_skills.load(name)
            if not prompt.startswith("[未知"):
                shared.setdefault("loaded_skills", []).append(name)
                injections.append(prompt)
                continue
        # 当作知识库名：检索
        if not default_store.get(name):
            default_store.load(name)
        if default_store.get(name):
            hits = query_kb(name, user_text, top_k=4)
            if hits:
                parts = [f"【知识库 {name} 相关片段】"]
                for i, h in enumerate(hits, 1):
                    parts.append(f"片段{i}（来源 {h['source']}）：{h['text']}")
                injections.append("\n".join(parts))
                shared.setdefault("kb_used", []).append(name)
        else:
            injections.append(f"[提示] @{name} 既非已注册 Skill 也无对应知识库；"
                              f"可先用 upload_doc 上传文档到知识库「{name}」，或检查 Skill 名。")
    return "\n\n".join(injections)
