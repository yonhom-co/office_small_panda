"""upload_data 工具 —— 让 Agent 自主上传 CSV/Excel 并解析为数据集。

补齐阶段1 步骤2：把文件接入暴露为工具，而非只能由调用方预先 ingest。
Agent 可通过本工具上传数据路径，自动生成元数据并设为 current_dataset。
"""
from __future__ import annotations

from .base import Tool, default_registry
from ..dataset import ingest, meta_to_text


def _upload_data(params: dict, shared: dict) -> str:
    path = params["path"]
    name = params.get("name")
    try:
        meta = ingest(path, shared, name=name)
    except Exception as e:
        return f"[上传失败] {type(e).__name__}: {e}"
    return f"已加载数据集「{meta['name']}」（{meta['rows']} 行 × {meta['cols']} 列），已设为当前数据集。\n\n" + meta_to_text(meta)


upload_data_tool = Tool(
    name="upload_data",
    description=(
        "上传 CSV/Excel 文件并解析为数据集。传 path（文件路径），可选 name（自定义数据集名）。"
        "解析后自动设为当前数据集 df，并返回字段元信息（类型/空值/样例/数值范围）。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "CSV/Excel 文件路径"},
            "name": {"type": "string", "description": "自定义数据集名（可选）"},
        },
        "required": ["path"],
    },
    executor=_upload_data,
)

default_registry.register(upload_data_tool)
