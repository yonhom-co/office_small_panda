"""plan 工具 —— 让 Agent 在循环中自主产出/更新执行计划。

补齐阶段2 步骤1：plan 不仅是 run_with_plan 的预编排，也注册为 Agent 可调用工具。
Agent 可在循环中调用 plan 产出或修订计划，写入 shared["plan"]，供追溯与 Replan。
"""
from __future__ import annotations

from .base import Tool, default_registry
from ..plan import make_plan, plan_to_text


def _plan(params: dict, shared: dict) -> str:
    goal = params["goal"]
    plan = make_plan(goal, context_extra=params.get("context", ""))
    shared["plan"] = plan
    shared["plan_text"] = plan_to_text(plan)
    return f"已产出/更新执行计划：\n{shared['plan_text']}"


plan_tool = Tool(
    name="plan",
    description=(
        "产出或更新一份结构化执行计划。传 goal（任务目标），可选 context（补充背景）。"
        "计划写入共享状态供追溯。复杂任务开始时或需要调整方向时调用。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "goal": {"type": "string", "description": "要规划的任务目标"},
            "context": {"type": "string", "description": "补充背景（可选）"},
        },
        "required": ["goal"],
    },
    executor=_plan,
)

default_registry.register(plan_tool)
