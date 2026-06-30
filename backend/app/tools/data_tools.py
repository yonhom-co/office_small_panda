"""read_data_meta 工具 —— 查看已上传数据的结构与元信息。"""
from __future__ import annotations

from .base import Tool, default_registry
from ..dataset import meta_to_text


def _read_data_meta(params: dict, shared: dict) -> str:
    datasets = shared.get("datasets", {})
    if not datasets:
        return "尚未上传数据集。请先上传 CSV/Excel。"
    name = params.get("name") or shared.get("current_dataset")
    if name and name in datasets:
        return meta_to_text(datasets[name])
    # 列出全部
    lines = [f"共 {len(datasets)} 个数据集："]
    for n, m in datasets.items():
        lines.append(f"  - {n}（{m['rows']} 行 × {m['cols']} 列）")
    lines.append("调用 read_data_meta 并传 name=<数据集名> 查看详情。")
    return "\n".join(lines)


read_data_meta_tool = Tool(
    name="read_data_meta",
    description="查看已上传数据集的元信息：行列数、字段名/类型/空值/样例/数值范围。可选传 name 指定数据集。",
    input_schema={
        "type": "object",
        "properties": {"name": {"type": "string", "description": "数据集名称；不传则列出全部"}},
        "required": [],
    },
    executor=_read_data_meta,
)

default_registry.register(read_data_meta_tool)
