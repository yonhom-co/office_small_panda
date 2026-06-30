"""run_code 工具 —— 在沙箱执行 LLM 生成的 Python。"""
from __future__ import annotations

from .base import Tool, default_registry
from ..sandbox import run_code
from ..dataset import WORKDIR


def _run_code(params: dict, shared: dict) -> str:
    code = params["code"]
    datasets = shared.get("datasets", {})
    cur = shared.get("current_dataset")
    parquet = datasets.get(cur, {}).get("path") if cur else None

    res = run_code(code, parquet)
    shared.setdefault("charts", []).extend(res["charts"])

    parts = []
    if res["stdout"].strip():
        parts.append("stdout:\n" + res["stdout"].strip()[-4000:])  # 截断防膨胀
    if res["charts"]:
        parts.append("生成的图表：" + ", ".join(res["charts"]))
    if res["error"]:
        parts.append("[错误]\n" + res["error"][-4000:])
        parts.append("请根据错误修正代码后重试。")
    else:
        parts.append("（代码执行成功，如需进一步分析请继续；若已得到结论可用 export_report 生成报告。）")
    return "\n\n".join(parts)


run_code_tool = Tool(
    name="run_code",
    description=(
        "在隔离沙箱中执行 Python 代码进行数据清洗、分析、预测、可视化。"
        "环境已预装 pandas(pd)/numpy(np)/matplotlib(plt,Agg后端)/sklearn；"
        "若已上传数据，DataFrame 变量 df 已加载。"
        "保存图表：matplotlib 用 plt.savefig 或 _save_fig()；plotly 用 _save_plotly(fig)。"
        "代码会在受限白名单环境中运行，禁网。"
    ),
    input_schema={
        "type": "object",
        "properties": {"code": {"type": "string", "description": "要执行的 Python 代码"}},
        "required": ["code"],
    },
    executor=_run_code,
)

default_registry.register(run_code_tool)
