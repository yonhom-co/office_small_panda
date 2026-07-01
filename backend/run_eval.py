"""Agent 评测集 + 基线（补齐阶段6 步骤3）。

评测维度：
- 工具调用准确率：是否调用了必要工具、顺序是否合理、有无滥用
- 报告可用率：是否生成报告、含图表、章节完整
- 引用真实性：结论是否基于真实数据（含具体数字）
- token 成本：每次任务的消耗

用例集：3 个典型场景（数据分析/异常检测/RAG 邮件）。
评判：结构化检查（必要步骤命中 + 产物完整性），输出基线分数。

用法：.venv/bin/python backend/run_eval.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# 在最早期设离线 env，确保主进程与子进程都不联网加载 embedding
import os as _os
_os.environ.setdefault("HF_HUB_OFFLINE", "1")
_os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent))
PROJECT_ROOT = Path(__file__).resolve().parent.parent

def _abs(p: str) -> str:
    return p if Path(p).is_absolute() else str(PROJECT_ROOT / p)

from app.dataset import ingest  # noqa: E402
from app.harness import build_flow  # noqa: E402
import app.tools_registry  # noqa: E402,F401  触发工具注册（side effect）

# 评测用例：每个含 goal、必要工具、验收检查
CASES = [
    {
        "id": "data_analysis",
        "goal": "分析各区域销售趋势与异常，生成HTML报告",
        "csv": "data/sample_sales.csv",
        "required_tools": {"read_data_meta", "run_code", "export_report"},
        "expect_report": True,
    },
    {
        "id": "rag_email",
        "goal": "基于 @公司介绍 写一封商务合作邮件",
        "csv": None,
        "doc": ("data/company_intro.txt", "公司介绍"),
        "required_tools": set(),  # @触发自动检索，不强制工具
        "expect_report": False,
    },
]


def run_case(case: dict) -> dict:
    """跑单个用例，返回评测结果。"""
    shared = {"messages": [{"role": "user", "content": case["goal"]}],
              "max_steps": 18}
    if case.get("csv"):
        ingest(_abs(case["csv"]), shared)
    if case.get("doc"):
        from app.knowledge_base import ingest_document
        ingest_document(_abs(case["doc"][0]), kb=case["doc"][1])

    flow = build_flow()
    flow.run(shared)

    trace = [t["name"] for t in shared.get("trace", [])]
    tools_used = set(trace)
    # 工具调用准确率：必要工具命中率
    required = case["required_tools"]
    hit = len(required & tools_used) if required else 1
    accuracy = hit / len(required) if required else 1.0
    # 报告可用率
    has_report = bool(shared.get("report_path"))
    report_ok = has_report if case["expect_report"] else True
    # 引用真实性：结果中是否含数字
    result = shared.get("result", "")
    has_numbers = any(c.isdigit() for c in result)
    # token 成本
    tokens = shared.get("token_stats", {})
    # 无滥用：同一工具连续调用 ≤ 5 次
    abuse = any(trace.count(t) > 5 for t in set(trace) if t not in
                ("end_turn", "max_steps_reached", "context_compressed"))

    score = (accuracy + (1.0 if report_ok else 0) + (1.0 if has_numbers else 0)
             + (1.0 if not abuse else 0)) / 4
    return {
        "case": case["id"],
        "accuracy": round(accuracy, 2),
        "report_ok": report_ok,
        "has_real_numbers": has_numbers,
        "no_abuse": not abuse,
        "token_input": tokens.get("input", 0),
        "token_output": tokens.get("output", 0),
        "steps": shared.get("step", 0),
        "tools": trace,
        "score": round(score, 2),
    }


def _run_case_subprocess(case: dict) -> dict:
    """在子进程中跑单个用例，隔离 embedding/torch 状态污染。"""
    import json as _json
    import subprocess as _sp
    import sys as _sys
    # 子进程 cwd=backend（脚本所在目录）；-c 模式不自动加 cwd，故显式 insert
    # 显式设离线 env，确保 transformers 不联网（子进程可能未继承父 env）
    code = (
        "import sys, os; sys.path.insert(0, os.getcwd())\n"
        "os.environ['HF_HUB_OFFLINE'] = '1'; os.environ['TRANSFORMERS_OFFLINE'] = '1'\n"
        "from run_eval import run_case, CASES_BY_ID\n"
        f"import json; print('@@RESULT@@' + json.dumps(run_case(CASES_BY_ID[{case['id']!r}])))\n"
    )
    try:
        # 显式传 env 给子进程，确保 HF 离线标志继承
        sub_env = {**_os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
        proc = _sp.run([_sys.executable, "-c", code],
                       capture_output=True, text=True, timeout=300,
                       cwd=str(Path(__file__).resolve().parent.parent),
                       env=sub_env)
        out = proc.stdout
        marker = "@@RESULT@@"
        if marker in out:
            return _json.loads(out.split(marker)[-1].strip())
        return {"case": case["id"], "score": 0.0,
                "error": (proc.stderr or out)[-500:], "accuracy": 0,
                "report_ok": False, "has_real_numbers": False, "no_abuse": False,
                "token_input": 0, "token_output": 0, "steps": 0, "tools": []}
    except Exception as e:
        return {"case": case["id"], "score": 0.0, "error": str(e),
                "accuracy": 0, "report_ok": False, "has_real_numbers": False,
                "no_abuse": False, "token_input": 0, "token_output": 0, "steps": 0, "tools": []}


CASES_BY_ID = {c["id"]: c for c in CASES}


def main() -> dict:
    results = []
    for case in CASES:
        print(f"\n=== 评测用例 {case['id']} ===")
        print(f"目标: {case['goal']}")
        r = _run_case_subprocess(case)
        if "error" in r:
            print(f"[用例失败] {r['error'][:200]}")
        print(f"准确率: {r['accuracy']} | 报告: {r['report_ok']} | "
              f"引用数字: {r['has_real_numbers']} | 无滥用: {r['no_abuse']}")
        print(f"token: in={r['token_input']} out={r['token_output']} | 步数: {r['steps']}")
        print(f"综合分: {r['score']}")
        results.append(r)

    avg = round(sum(r["score"] for r in results) / len(results), 2)
    print(f"\n{'='*40}\n基线综合分: {avg} / 1.00")
    return {"cases": results, "baseline": avg}


if __name__ == "__main__":
    main()
