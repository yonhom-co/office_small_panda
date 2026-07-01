"""知识库 —— ingestion + 向量检索 + 多知识库管理。

流程：上传文档（PDF/Word/TXT/Markdown）→ 切分 → embedding → 入向量索引。
检索：query_kb 工具语义检索，返回最相关片段。

存储：阶段3 用本地 JSON 持久化的简易向量索引（不依赖外部 Qdrant，便于验收）。
阶段5 可切换 Qdrant 实现（接口已留 KBStore）。

多知识库：按 kb_name 隔离，支持个人/团队知识库。
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from .dataset import WORKDIR
from .embedding import embed, embed_one

KB_DIR = Path(os.getenv("RACCOON_KB_DIR", WORKDIR / "knowledge_base"))
KB_DIR.mkdir(parents=True, exist_ok=True)

CHUNK_SIZE = int(os.getenv("RACCOON_CHUNK_SIZE", "500"))     # 字符数
CHUNK_OVERLAP = int(os.getenv("RACCOON_CHUNK_OVERLAP", "80"))


@dataclass
class Chunk:
    id: str
    kb: str
    source: str           # 来源文件名
    text: str
    vector: list[float] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


def _split_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """按字符数切分（中文友好），带重叠。"""
    if not text.strip():
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def _extract_text(path: str) -> str:
    """从文件提取文本：txt/md 直接读；PDF/Word 用对应库。"""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in (".txt", ".md"):
        return p.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
            return "\n".join(page.extract_text() or "" for page in PdfReader(str(p)))
        except Exception as e:
            return f"[PDF 解析失败: {e}]"
    if suffix in (".docx", ".doc"):
        try:
            from docx import Document
            doc = Document(str(p))
            return "\n".join(para.text for para in doc.paragraphs)
        except Exception as e:
            return f"[Word 解析失败: {e}]"
    # 未知类型尝试当文本读
    return p.read_text(encoding="utf-8", errors="ignore")


class KBStore:
    """向量存储抽象。默认本地 JSON 实现；阶段5 可换 Qdrant。"""

    def __init__(self) -> None:
        self._kbs: dict[str, list[Chunk]] = {}

    def add(self, chunks: list[Chunk]) -> None:
        for c in chunks:
            self._kbs.setdefault(c.kb, []).append(c)

    def get(self, kb: str) -> list[Chunk]:
        return self._kbs.get(kb, [])

    def list_kbs(self) -> list[str]:
        return list(self._kbs.keys())

    def query(self, kb: str, query_vec: list[float], top_k: int = 4) -> list[Chunk]:
        """余弦相似度检索（向量已归一化，点积即余弦）。"""
        chunks = self.get(kb)
        if not chunks:
            return []
        scored = []
        for c in chunks:
            if not c.vector:
                continue
            score = sum(a * b for a, b in zip(c.vector, query_vec))
            scored.append((score, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:top_k]]

    def save(self, kb: str) -> Path:
        """持久化某知识库到 JSON。"""
        path = KB_DIR / f"{kb}.json"
        data = [asdict(c) for c in self.get(kb)]
        path.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
        return path

    def load(self, kb: str) -> bool:
        path = KB_DIR / f"{kb}.json"
        if not path.exists():
            return False
        data = json.loads(path.read_text(encoding="utf-8"))
        self._kbs[kb] = [Chunk(**d) for d in data]
        return True


# 全局默认存储
default_store = KBStore()


def ingest_document(path: str, kb: str = "default", source_name: str | None = None) -> dict:
    """ingestion：提取文本→切分→embedding→入库。返回元信息。"""
    text = _extract_text(path)
    src = source_name or Path(path).name
    pieces = _split_text(text)
    if not pieces:
        return {"kb": kb, "source": src, "chunks": 0}
    vectors = embed(pieces)
    chunks = [
        Chunk(id=str(uuid.uuid4()), kb=kb, source=src, text=p, vector=v)
        for p, v in zip(pieces, vectors)
    ]
    default_store.add(chunks)
    default_store.save(kb)
    return {"kb": kb, "source": src, "chunks": len(chunks),
            "chars": len(text), "kb_list": default_store.list_kbs()}


def query_kb(kb: str, question: str, top_k: int = 4) -> list[dict]:
    """检索：返回最相关片段。"""
    if not default_store.get(kb):
        default_store.load(kb)
    qvec = embed_one(question)
    hits = default_store.query(kb, qvec, top_k=top_k)
    return [{"source": h.source, "text": h.text} for h in hits]
