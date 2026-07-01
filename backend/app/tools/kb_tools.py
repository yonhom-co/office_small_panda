"""知识库工具 —— upload_doc（ingestion）+ query_kb（检索）。"""
from __future__ import annotations

from .base import Tool, default_registry
from ..knowledge_base import ingest_document, query_kb, default_store


def _upload_doc(params: dict, shared: dict) -> str:
    path = params["path"]
    kb = params.get("kb", "default")
    info = ingest_document(path, kb=kb)
    if info["chunks"] == 0:
        return f"[上传失败] 未能从 {path} 提取文本"
    shared.setdefault("kb_list", [])
    if kb not in shared["kb_list"]:
        shared["kb_list"].append(kb)
    return (f"已将文档「{info['source']}」加入知识库「{kb}」："
            f"{info['chunks']} 个片段，{info['chars']} 字符。可用 query_kb 检索。")


def _query_kb(params: dict, shared: dict) -> str:
    kb = params.get("kb", "default")
    question = params["question"]
    top_k = params.get("top_k", 4)
    hits = query_kb(kb, question, top_k=top_k)
    if not hits:
        kbs = default_store.list_kbs() or shared.get("kb_list", [])
        return f"[知识库「{kb}」无内容] 可用知识库：{kbs}"
    parts = [f"知识库「{kb}」检索到 {len(hits)} 条相关片段："]
    for i, h in enumerate(hits, 1):
        parts.append(f"\n--- 片段{i}（来源：{h['source']}）---\n{h['text']}")
    return "\n".join(parts)


upload_doc_tool = Tool(
    name="upload_doc",
    description=(
        "上传文档到知识库（PDF/Word/TXT/Markdown），自动切分、向量化、入库。"
        "传 path（文件路径），可选 kb（知识库名，默认 default）。"
        "入库后可用 query_kb 语义检索。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "kb": {"type": "string", "description": "知识库名，默认 default"},
        },
        "required": ["path"],
    },
    executor=_upload_doc,
)


query_kb_tool = Tool(
    name="query_kb",
    description=(
        "在知识库中语义检索与问题最相关的片段。传 question（问题/关键词），"
        "可选 kb（知识库名，默认 default）、top_k（返回条数，默认4）。"
        "用于基于上传文档的问答；引用检索到的原文片段作答。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "kb": {"type": "string", "description": "知识库名，默认 default"},
            "top_k": {"type": "integer", "description": "返回条数，默认4"},
        },
        "required": ["question"],
    },
    executor=_query_kb,
)

default_registry.register(upload_doc_tool)
default_registry.register(query_kb_tool)
