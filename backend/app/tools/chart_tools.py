"""make_chart 工具 —— 声明式快速生成常用图表。

与 run_code 互补：run_code 跑任意 Python（灵活但需写代码）；
make_chart 传「类型+列」直接出图（快速、稳定），适合标准 EDA 图。
"""
from __future__ import annotations

import textwrap

from .base import Tool, default_registry
from ..sandbox import run_code


def _make_chart(params: dict, shared: dict) -> str:
    chart_type = params["chart_type"]
    x = params.get("x")
    y = params.get("y")
    title = params.get("title", "")

    # 生成 plotly 代码并复用沙箱执行
    code = textwrap.dedent(f"""
        import plotly.express as px
        fig = None
        ct = {chart_type!r}
        if ct == "line":
            fig = px.line(df, x={x!r}, y={y!r}, title={title!r})
        elif ct == "bar":
            fig = px.bar(df, x={x!r}, y={y!r}, title={title!r})
        elif ct == "scatter":
            fig = px.scatter(df, x={x!r}, y={y!r}, title={title!r})
        elif ct == "histogram":
            col = {x!r} or {y!r}
            fig = px.histogram(df, x=col, title={title!r})
        elif ct == "box":
            fig = px.box(df, x={x!r}, y={y!r}, title={title!r})
        elif ct == "pie":
            fig = px.pie(df, names={x!r}, values={y!r}, title={title!r})
        else:
            print("未知图表类型:", ct)
        if fig is not None:
            path = _save_plotly(fig, name=ct)
            print("生成", ct, "图：", path)
    """)
    res = run_code(code, shared.get("datasets", {}).get(shared.get("current_dataset", ""), {}).get("path"))
    if res["charts"]:
        shared.setdefault("charts", []).extend(res["charts"])
        return f"已生成 {chart_type} 图：{res['charts'][-1]}"
    return f"图表生成失败：{res.get('error') or '未知原因'}"


make_chart_tool = Tool(
    name="make_chart",
    description="快速生成常用图表（line/bar/scatter/histogram/box/pie）。传 chart_type 与列名即可，基于已上传数据 df。",
    input_schema={
        "type": "object",
        "properties": {
            "chart_type": {"type": "string", "enum": ["line", "bar", "scatter", "histogram", "box", "pie"]},
            "x": {"type": "string", "description": "x 轴列名"},
            "y": {"type": "string", "description": "y 轴列名"},
            "title": {"type": "string", "description": "图表标题"},
        },
        "required": ["chart_type"],
    },
    executor=_make_chart,
)

default_registry.register(make_chart_tool)
