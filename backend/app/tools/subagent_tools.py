"""dispatch_subagent 工具 —— 主 harness 委派子任务给隔离子代理。"""
from __future__ import annotations

from .base import Tool, default_registry
from ..subagent import dispatch, dispatch_parallel, SUBAGENT_TYPES


def _dispatch_subagent(params: dict, shared: dict) -> str:
    # 并发模式：tasks 列表
    tasks = params.get("tasks")
    if tasks:
        conclusions = dispatch_parallel(tasks, shared)
        parts = [f"[并行委派 {len(tasks)} 个子代理]"]
        for t, c in zip(tasks, conclusions):
            parts.append(f"\n--- {t.get('agent_type','data_analyst')}：{t['task'][:40]} ---\n{c}")
        return "\n".join(parts)

    # 单任务模式
    task = params["task"]
    agent_type = params.get("agent_type", "data_analyst")
    if agent_type not in SUBAGENT_TYPES:
        return f"未知子代理类型：{agent_type}；可选：{list(SUBAGENT_TYPES.keys())}"
    conclusion = dispatch(task, shared, agent_type=agent_type)
    return f"[子代理 {agent_type} 结论]\n{conclusion}"


dispatch_subagent_tool = Tool(
    name="dispatch_subagent",
    description=(
        "把子任务委派给隔离子代理执行，只回传结论（不污染主上下文）。"
        "适合重活：数据分析、深度研究、文案撰写。"
        "单任务：传 task + agent_type（data_analyst/researcher/writer）。"
        "并发：传 tasks 列表（每项含 task 与 agent_type），多个子代理并行执行。"
        "子代理生成的图表会自动并入主报告。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "委派给子代理的子任务描述（单任务模式）"},
            "agent_type": {"type": "string", "enum": list(SUBAGENT_TYPES.keys()),
                           "description": "子代理类型，默认 data_analyst"},
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string"},
                        "agent_type": {"type": "string", "enum": list(SUBAGENT_TYPES.keys())},
                    },
                    "required": ["task"],
                },
                "description": "并发模式：多个子任务并行执行",
            },
        },
        "required": [],
    },
    executor=_dispatch_subagent,
)

default_registry.register(dispatch_subagent_tool)
