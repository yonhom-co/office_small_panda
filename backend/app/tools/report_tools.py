"""export_report 工具 —— 将分析过程与图表组装为 HTML 报告。

模型在分析完成后调用本工具，传入标题、发现摘要、章节内容。工具读取 shared 中的图表，
生成自包含 HTML（图表以 base64 内嵌，便于下载/预览）。
"""
from __future__ import annotations

import base64
import html
import os
import uuid
from pathlib import Path

from .base import Tool, default_registry
from ..dataset import WORKDIR


def _img_b64(path: str) -> str:
    data = Path(path).read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode()


def _export_report(params: dict, shared: dict) -> str:
    title = params.get("title", "数据分析报告")
    summary = params.get("summary", "")
    sections = params.get("sections", [])
    charts = shared.get("charts", [])

    parts = [f"<h1>{html.escape(title)}</h1>"]
    if summary:
        parts.append(f"<h2>摘要</h2><p>{html.escape(summary)}</p>")

    for sec in sections:
        heading = sec.get("heading", "")
        body = sec.get("content", "")
        parts.append(f"<h2>{html.escape(heading)}</h2>")
        parts.append(f"<div>{html.escape(body).replace(chr(10), '<br>')}</div>")

    if charts:
        parts.append("<h2>图表</h2>")
        for c in charts:
            try:
                parts.append(f'<img src="{_img_b64(c)}" style="max-width:100%;">')
            except Exception:
                parts.append(f"<p>[图表缺失: {c}]</p>")

    # 追溯记录
    trace = shared.get("trace", [])
    if trace:
        parts.append("<h2>执行追溯</h2><ul>")
        for t in trace:
            parts.append(f"<li>步骤{t.get('step')}：{html.escape(str(t.get('name')))}</li>")
        parts.append("</ul>")

    css = """
    <style>
      body{font-family:-apple-system,'PingFang SC',sans-serif;max-width:900px;margin:40px auto;padding:0 20px;color:#222}
      h1{color:#c0392b;border-bottom:3px solid #c0392b;padding-bottom:10px}
      h2{color:#2c3e50;margin-top:30px}
      img{border:1px solid #eee;margin:10px 0}
      ul{background:#f9f9f9;padding:15px 30px;border-radius:6px}
    </style>"""
    doc = f"<!DOCTYPE html><html><head><meta charset='utf-8'>{css}</head><body>{''.join(parts)}</body></html>"

    out_dir = WORKDIR / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"report_{uuid.uuid4().hex[:8]}.html"
    out_path = out_dir / name
    out_path.write_text(doc, encoding="utf-8")
    shared["report_path"] = str(out_path)
    return f"报告已生成：{out_path}\n（含 {len(charts)} 张图表，{len(sections)} 个章节，自包含 HTML）"


export_report_tool = Tool(
    name="export_report",
    description=(
        "生成 HTML 数据分析报告。分析完成后调用。"
        "传 title（标题）、summary（发现摘要）、sections（章节列表，每项含 heading 与 content）。"
        "已生成的图表会自动嵌入。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "summary": {"type": "string", "description": "核心发现摘要"},
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "heading": {"type": "string"},
                        "content": {"type": "string"},
                    },
                },
            },
        },
        "required": ["title"],
    },
    executor=_export_report,
)

default_registry.register(export_report_tool)
