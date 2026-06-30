"""阶段 2 端到端验收脚本。

场景：输入"分析经营数据并做一份给管理层的汇报 PPT"，
  Plan Mode 出计划 → 审批（默认 auto_approve，可改 CLI 交互）→
  主 harness 执行（可委派子代理）→ 产出 PPT。

验证：
  - Plan Mode 产出可读计划
  - 人机共决策入口（approval_fn 可注入；auto_approve 用于自动化）
  - 子代理委派（dispatch_subagent）隔离上下文
  - 上下文压缩（maybe_compress）
  - 过程追溯（CheckpointStore 快照）
  - PPT 交付物（gen_ppt）

用法：
  .venv/bin/python backend/run_acceptance_stage2.py            # auto_approve
  .venv/bin/python backend/run_acceptance_stage2.py --interactive  # CLI 审批
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.dataset import ingest  # noqa: E402
from app.plan_mode import run_with_plan  # noqa: E402
from app.checkpoint import CheckpointStore  # noqa: E402
import app.tools_registry  # noqa: E402,F401  触发工具注册


def main(csv_path: str = "data/sample_sales.csv",
         goal: str | None = None,
         interactive: bool = False) -> dict:
    goal = goal or "分析这份经营数据，找出销售趋势与异常，做一份给管理层的汇报 PPT（含图表）。"

    ckpt = CheckpointStore()
    shared = {
        "max_steps": 20,
        "checkpoint": ckpt,
        "task_context": "数据集为各区域月度销售数据，需产出管理层汇报 PPT。",
    }
    meta = ingest(csv_path, shared)
    print(f"已加载数据集：{meta['name']}（{meta['rows']} 行 × {meta['cols']} 列）")
    print(f"任务目标：{goal}")
    print(f"会话 checkpoint：{ckpt.session_id}")
    print("=" * 60)

    run_with_plan(goal, shared, checkpoint=ckpt, auto_approve=not interactive)

    print("=" * 60)
    print("【执行计划】")
    print(shared.get("plan_text", "(无计划)"))
    print("\n【最终回复】")
    print(shared.get("result", "(空)"))
    print("\n【PPT 路径】", shared.get("ppt_path", "(未生成)"))
    print("【HTML 报告】", shared.get("report_path", "(未生成)"))
    print("【图表数量】", len(shared.get("charts", [])))
    print("\n【子代理调用记录】")
    for s in shared.get("subagent_log", []):
        print(f"  - {s['type']}：{s['task'][:60]}... | 步骤 {len(s['steps'])} | 图表 {s['charts']}")
    print("\n【主 harness 追溯】")
    for t in shared.get("trace", []):
        print(f"  步骤{t.get('step')} → {t.get('name')}")
    print("\n【Checkpoint 快照】")
    for s in ckpt.summary():
        print(f"  步骤{s['step']} {s['action']}：{s['note'][:60]}")
    return shared


if __name__ == "__main__":
    interactive = "--interactive" in sys.argv
    main(interactive=interactive)
