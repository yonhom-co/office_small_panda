"""Plan Mode —— 人机共决策（复刻「DeepResearch 可交互/可调整」）。

流程：
1. PlanNode：让 LLM 产出结构化计划（步骤列表），写入 shared["plan"]。
2. 暂停，等待人类审批（HumanGate）： approve / modify / reject。
3. approve → 进入执行 harness；modify → 用人类修改后的计划 replan 后执行；
   reject → 终止。

审批接口设计为可注入的回调，使其既能 CLI 交互，也能后续接 Web SSE。
"""
from __future__ import annotations

from typing import Any, Callable

from .llm import chat, MODEL_PLAN
from .context import build_system

PLAN_SYSTEM = """你是办公小浣熊的任务规划器。用户给出一个复杂任务后，你要产出一个清晰、可执行的计划。

要求：
- 把任务拆为 3-6 个有序步骤，每步说明要做什么、用哪个工具/子代理。
- 标注哪些步骤需要人类确认（关键决策点）。
- 识别可并行或可委派给子代理的子任务。
- 输出严格 JSON：{"goal": "...", "steps": [{"id":1,"action":"...","tool":"...","need_human":false}], "notes":"..."}
"""


def make_plan(goal: str, context_extra: str = "") -> dict:
    """让 LLM 产出结构化计划。"""
    resp = chat(
        model=MODEL_PLAN,
        max_tokens=1500,
        system=build_system(PLAN_SYSTEM, extra=context_extra),
        messages=[{"role": "user", "content": f"任务：{goal}\n\n请产出执行计划（JSON）。"}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    import json, re
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {"goal": goal, "steps": [{"id": 1, "action": goal, "tool": "auto", "need_human": False}],
                "notes": "（计划解析失败，直接执行）", "raw": text}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"goal": goal, "steps": [{"id": 1, "action": goal, "tool": "auto", "need_human": False}],
                "notes": "（计划解析失败，直接执行）", "raw": text}


# 审批结果类型
APPROVE = "approve"
MODIFY = "modify"
REJECT = "reject"


def plan_to_text(plan: dict) -> str:
    """把计划渲染为给人类看的文本。"""
    lines = [f"目标：{plan.get('goal', '')}"]
    for s in plan.get("steps", []):
        flag = " [需人类确认]" if s.get("need_human") else ""
        lines.append(f"  {s.get('id')}. {s.get('action')}（工具: {s.get('tool','auto')}）{flag}")
    if plan.get("notes"):
        lines.append(f"备注：{plan['notes']}")
    return "\n".join(lines)


# 审批回调签名：(plan_text, plan) -> (decision, modified_plan_or_None)
ApprovalFn = Callable[[str, dict], tuple[str, dict | None]]


def cli_approval(plan_text: str, plan: dict) -> tuple[str, dict | None]:
    """默认 CLI 审批：读 stdin。"""
    print("\n" + "=" * 60)
    print("【Plan Mode —— 请审批执行计划】")
    print("=" * 60)
    print(plan_text)
    print("=" * 60)
    choice = input("批准(approve) / 修改(modify) / 拒绝(reject)？ [a/m/r]: ").strip().lower()
    if choice in ("m", "modify"):
        print("请输入修改后的目标与步骤说明（空行结束）：")
        lines = []
        while True:
            line = input()
            if not line:
                break
            lines.append(line)
        modified = dict(plan)
        modified["notes"] = (modified.get("notes", "") + "\n人类修改：" + "\n".join(lines)).strip()
        modified["human_modified"] = True
        return MODIFY, modified
    if choice in ("r", "reject"):
        return REJECT, None
    return APPROVE, None
