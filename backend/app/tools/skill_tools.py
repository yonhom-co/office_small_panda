"""load_skill 工具 —— Agent 按需载入 Skill 指令包。"""
from __future__ import annotations

from .base import Tool, default_registry
from ..skills import default_skills


def _load_skill(params: dict, shared: dict) -> str:
    name = params["name"]
    prompt = default_skills.load(name)
    # 把载入的 Skill 指令追加到系统提示（动态注入）
    if not prompt.startswith("[未知 Skill]"):
        cur = shared.get("system", "")
        shared["system"] = (cur + "\n\n" + prompt) if cur else prompt
        shared.setdefault("loaded_skills", []).append(name)
    return prompt


load_skill_tool = Tool(
    name="load_skill",
    description=(
        "按需载入一个 Skill 能力包到上下文。传 name（如 writing）。"
        "载入后相关领域能力生效。也可由 @能力名 触发自动载入。"
        "可用 Skill 见返回或调用 load_skill 不带 name 列出。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Skill 名称，如 writing"},
        },
        "required": [],
    },
    executor=_load_skill,
)

default_registry.register(load_skill_tool)
