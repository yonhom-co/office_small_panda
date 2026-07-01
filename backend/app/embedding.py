"""本地 Embedding —— 不依赖 ARK（账号无可用 embedding 模型，见报告 §2.5 注意事项 4）。

策略：chat 走 ARK Anthropic、embedding 走本地 sentence-transformers，分而治之。

模型选择（按可用性降级）：
- 首选 bge-m3（BAAI/bge-m3，中文好、1024维），但需联网下载。
- 实测当前环境无法连接 huggingface.co 下载 bge-m3，故默认降级为
  sentence-transformers/all-MiniLM-L6-v2（已本地缓存、384维、不联网）。
- 私有化可预下载 bge-m3 并设 EMBED_MODEL_DIR，或通过 EMBED_MODEL 切换。

降级不影响 RAG 机制验证（仍可语义检索），仅中文精度略降。
"""
from __future__ import annotations

import os
from functools import lru_cache

# 默认 MiniLM（本地缓存可用）；设 EMBED_MODEL=BAAI/bge-m3 切换（需联网/预下载）
EMBED_MODEL_NAME = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
EMBED_MODEL_DIR = os.getenv("EMBED_MODEL_DIR")  # 私有化：本地模型路径

# 离线模式：避免每次加载都尝试联网检查
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


@lru_cache(maxsize=1)
def _get_model():
    """懒加载 sentence-transformers 模型（单例）。强制离线，避免联网卡顿。"""
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    from sentence_transformers import SentenceTransformer
    name_or_path = EMBED_MODEL_DIR or EMBED_MODEL_NAME
    return SentenceTransformer(
        name_or_path, device=os.getenv("EMBED_DEVICE", "cpu"),
        model_kwargs={"local_files_only": True},
    )


def embed(texts: list[str]) -> list[list[float]]:
    """对文本列表生成向量。"""
    if isinstance(texts, str):
        texts = [texts]
    model = _get_model()
    vecs = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
    return [v.tolist() for v in vecs]


def embed_one(text: str) -> list[float]:
    """单文本向量。"""
    return embed([text])[0]
