"""dispatch_subagent 工具 —— 主 harness 委派子任务给隔离子代理。"""
from __future__ import annotations

from .base import Tool, default_registry
from ..subagent import dispatch, SUBAGENT_TYPES


def _dispatch_subagent(params: dict, shared: dict) -> str:
    task = params["task"]
    agent_type = params.get("agent_type", "data_analyst")
    if agent_type not in SUBAGENT_TYPES:
        return f"未知子代理类型：{agent_type}；可选：{list(SUBAGENT_TYPES.keys())}"
    conclusion = dispatch(task, shared, agent_type=agent_type)
    return f"[子代理 {agent_type} 结论]\n{conclusion}"


dispatch_subagent_tool = Tool(
    name="dispatch_subagent",
    description=(
        "把一个独立子任务委派给隔离子代理执行，只回传结论（不污染主上下文）。"
        "适合重活：数据分析、深度研究、文案撰写。"
        "agent_type 可选：data_analyst（数据分析）/ researcher（深度研究）/ writer（文案）。"
        "传 task 描述子任务。子代理生成的图表会自动并入主报告。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "委派给子代理的子任务描述"},
            "agent_type": {"type": "string", "enum": list(SUBAGENT_TYPES.keys()),
                           "description": "子代理类型，默认 data_analyst"},
        },
        "required": ["task"],
    },
    executor=_dispatch_subagent,
)

default_registry.register(dispatch_subagent_tool)
