"""Replan + 分支重跑 —— 接入 checkpoint.load（补齐阶段2 步骤5）。

能力：
- branch_from(ckpt, step)：从某步快照重建 shared（分支起点）。
- replan(shared, new_goal)：在重建的 shared 上重新规划并执行，实现"改方向重跑"。
- resume_from(ckpt, step)：从某步快照恢复，原计划继续跑。

设计：PocketFlow 无内部不可恢复状态，shared 快照含 messages/step/todos/datasets 等，
重建后直接喂给 flow.run 即可从该点继续或重跑。这把 checkpoint.load 真正接入流程。
"""
from __future__ import annotations

from .checkpoint import CheckpointStore
from .harness import build_flow
from .plan import make_plan, plan_to_text


def branch_from(ckpt: CheckpointStore, step: int) -> dict:
    """从某步快照重建 shared，作为分支起点。返回新的 shared 副本。"""
    snap = ckpt.load(step)
    if snap is None:
        raise ValueError(f"无步骤 {step} 的快照")
    shared = dict(snap.get("shared", {}))
    # 重建需要的运行时对象（快照时跳过了 tools）
    from . import tools_registry
    shared.setdefault("tools", tools_registry.default_registry)
    shared.pop("abort", None)
    shared.pop("aborted", None)
    return shared


def replan(ckpt: CheckpointStore, step: int, new_goal: str, *, auto_approve: bool = True) -> dict:
    """从 step 快照分支，用新目标重新规划并执行。

    用于"跑到一半发现方向错了"：回退到某步，重新出计划，重新跑。
    """
    shared = branch_from(ckpt, step)
    # 重新规划
    plan = make_plan(new_goal, context_extra=shared.get("task_context", ""))
    shared["plan"] = plan
    shared["plan_text"] = plan_to_text(plan)
    # 注入新目标作为最新指示
    shared.setdefault("messages", []).append(
        {"role": "user", "content": f"【Replan】新目标：{new_goal}\n\n新计划：\n{shared['plan_text']}\n请按新计划执行。"}
    )
    ckpt.snapshot(shared, step=shared.get("step", 0), action="replan", note=new_goal[:100])
    flow = build_flow()
    flow.run(shared)
    return shared


def resume_from(ckpt: CheckpointStore, step: int) -> dict:
    """从 step 快照恢复，按原计划继续跑（不重新规划）。"""
    shared = branch_from(ckpt, step)
    flow = build_flow()
    flow.run(shared)
    return shared
