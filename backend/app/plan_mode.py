"""Plan Mode Harness —— 把 Plan Mode 与执行 harness 串联。

run_with_plan(goal, shared, approval_fn):
  1. make_plan 产出计划 → 写入 shared["plan"]
  2. 调 approval_fn 审批
     - APPROVE: 把计划注入执行上下文，进入执行 harness
     - MODIFY: 用修改后的计划进入执行
     - REJECT: 终止
  3. 执行 harness（单节点自环 tool-use 循环）跑完任务
  4. 返回 shared

这是「人机共决策」的落地：复杂任务先出方案、人类可改、再执行。
"""
from __future__ import annotations

from typing import Callable

from .harness import build_flow, SYSTEM_PROMPT
from .context import build_system
from .plan import make_plan, plan_to_text, APPROVE, MODIFY, REJECT, ApprovalFn, cli_approval
from .checkpoint import CheckpointStore


def run_with_plan(
    goal: str,
    shared: dict,
    *,
    approval_fn: ApprovalFn = cli_approval,
    checkpoint: CheckpointStore | None = None,
    auto_approve: bool = False,
) -> dict:
    """Plan Mode 全流程。

    auto_approve=True 时跳过人类审批（用于自动化测试/验收）。
    """
    # 1. 产出计划
    plan = make_plan(goal, context_extra=shared.get("task_context", ""))
    shared["plan"] = plan
    plan_text = plan_to_text(plan)
    shared["plan_text"] = plan_text
    if checkpoint:
        checkpoint.snapshot(shared, step=0, action="plan_created", note=plan_text)

    # 2. 审批
    if auto_approve:
        decision, modified = APPROVE, None
    else:
        decision, modified = approval_fn(plan_text, plan)

    if decision == REJECT:
        shared["result"] = "[任务被拒绝，未执行]"
        if checkpoint:
            checkpoint.snapshot(shared, step=0, action="rejected")
        return shared

    if decision == MODIFY and modified:
        shared["plan"] = modified
        shared["plan_text"] = plan_to_text(modified)
        if checkpoint:
            checkpoint.snapshot(shared, step=0, action="plan_modified", note=shared["plan_text"])

    # 3. 把计划注入执行上下文，组装用户消息
    plan_ctx = f"已批准的执行计划：\n{shared['plan_text']}\n\n请按计划执行，完成后用 export_report 或 gen_ppt 产出交付物。"
    shared.setdefault("messages", []).append({"role": "user", "content": f"{goal}\n\n{plan_ctx}"})
    shared["system"] = build_system(SYSTEM_PROMPT, extra=shared.get("task_context", ""))

    if checkpoint:
        checkpoint.snapshot(shared, step=0, action="plan_approved", note="进入执行")

    # 4. 执行 harness
    flow = build_flow()
    flow.run(shared)

    if checkpoint:
        checkpoint.snapshot(shared, step=shared.get("step", 0), action="done",
                            note=shared.get("result", "")[:200])
    return shared
