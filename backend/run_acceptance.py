"""阶段 1 端到端验收脚本。

流程：上传 sample_sales.csv → 自然语言提问 → Agent Harness 自主 tool-use 循环
→ 生成含图表的 HTML 报告 → 打印执行追溯。

用法：.venv/bin/python backend/run_acceptance.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# 确保以 backend/ 为根导入
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.dataset import ingest  # noqa: E402
from app.harness import build_flow  # noqa: E402
import app.tools_registry  # noqa: E402,F401  触发工具注册


def main(csv_path: str = "data/sample_sales.csv", question: str | None = None) -> dict:
    question = question or "分析各区域销售趋势，找出异常，生成一份含图表的报告。"

    shared = {
        "messages": [{"role": "user", "content": question}],
        "max_steps": 22,
    }
    # 上传数据
    meta = ingest(csv_path, shared)
    print(f"已加载数据集：{meta['name']}（{meta['rows']} 行 × {meta['cols']} 列）")
    print(f"用户提问：{question}\n")
    print("=" * 60)

    flow = build_flow()
    flow.run(shared)

    print("=" * 60)
    print("【最终回复】")
    print(shared.get("result", "(空)"))
    print("\n【报告路径】", shared.get("report_path", "(未生成)"))
    print("【图表数量】", len(shared.get("charts", [])))
    print("【Todo 清单】")
    for i, t in enumerate(shared.get("todos", []), 1):
        mark = "✓" if t["status"] == "done" else "○"
        print(f"  {i}. [{mark}] {t['content']}")
    print("\n【执行追溯（工具调用链）】")
    for t in shared.get("trace", []):
        print(f"  步骤{t.get('step')} → {t.get('name')}")
    return shared


if __name__ == "__main__":
    main()
