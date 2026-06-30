"""子代理委派 —— 隔离上下文，只回传结论（复刻 Claude Code Task/Sub-agent）。

设计：
- SubAgent：一个独立的 tool-use harness 实例，拥有自己的 shared 副本（隔离上下文）。
  主 harness 通过 dispatch_subagent 工具委派任务；子代理跑完后只把结论文本回传，
  不把内部工具调用历史灌入主上下文，保护主上下文不被淹没。
- SubAgentRegistry：预置几种子代理类型（数据分析 / 深度研究 / 文案），
  各自有专属系统提示与可用工具子集。
- 共享数据：子代理继承主 shared 的 datasets（只读引用），可写自己的 charts，
  产出图表路径回传主 shared。
"""
from __future__ import annotations

import copy
from typing import Any

from .harness import build_flow
from .context import build_system
from .llm import MODEL, MODEL_REASON


# 子代理类型 → (系统提示, 允许的工具名, 推荐模型)
SUBAGENT_TYPES: dict[str, dict] = {
    "data_analyst": {
        "system": (
            "你是数据分析子代理。专注完成委派的数据分析子任务：用 read_data_meta 了解数据，"
            "用 run_code 分析与画图，必要时用 make_chart。完成后用一段话总结结论与关键数字，"
            "并说明生成了哪些图表。不要生成报告（由主代理统一产出）。"
        ),
        "tools": {"read_data_meta", "run_code", "make_chart", "todo"},
        "model": MODEL_REASON,
    },
    "researcher": {
        "system": (
            "你是深度研究子代理。针对委派的研究子任务，自主多步分析数据、归纳发现，"
            "产出结构化结论（要点 + 证据 + 建议）。聚焦深度，不要生成最终报告。"
        ),
        "tools": {"read_data_meta", "run_code", "todo"},
        "model": MODEL_REASON,
    },
    "writer": {
        "system": (
            "你是文案/报告撰写子代理。根据委派的要点，撰写高质量中文文案或报告章节。"
        ),
        "tools": {"todo"},
        "model": MODEL,
    },
}


def dispatch(task: str, shared: dict, agent_type: str = "data_analyst",
             max_steps: int = 10) -> str:
    """委派一个子任务给隔离上下文的子代理，返回结论文本。

    子代理拥有独立 shared 副本；datasets 只读继承；产出的 charts 路径回传主 shared。
    """
    spec = SUBAGENT_TYPES.get(agent_type, SUBAGENT_TYPES["data_analyst"])

    # 独立 shared 副本（隔离上下文）：继承 datasets 与 checkpoints 配置，清空对话历史
    sub_shared = {
        "messages": [{"role": "user", "content": task}],
        "datasets": copy.deepcopy(shared.get("datasets", {})),
        "current_dataset": shared.get("current_dataset"),
        "todos": [],
        "trace": [],
        "step": 0,
        "max_steps": max_steps,
        "model": spec["model"],
        "system": build_system(spec["system"]),
        # 工具子集：用一个受限 registry
        "tools": _restricted_registry(spec["tools"]),
    }

    flow = build_flow()
    flow.run(sub_shared)

    # 收集子代理结论
    conclusion = sub_shared.get("result", "(子代理无输出)")
    new_charts = sub_shared.get("charts", [])
    if new_charts:
        shared.setdefault("charts", []).extend(new_charts)
        conclusion += f"\n[子代理生成图表 {len(new_charts)} 张]"

    # 子代理的 trace 摘要回传（供主代理追溯，但不灌入完整历史）
    sub_steps = [t["name"] for t in sub_shared.get("trace", [])]
    shared.setdefault("subagent_log", []).append({
        "type": agent_type, "task": task, "steps": sub_steps,
        "charts": len(new_charts),
    })
    return conclusion


def _restricted_registry(allowed_names: set[str]):
    """构建只含指定工具的子注册表。"""
    from .tools import ToolRegistry
    from . import tools_registry

    reg = ToolRegistry()
    for name in allowed_names:
        tool = tools_registry.default_registry.get(name)
        if tool:
            reg.register(tool)
    return reg
