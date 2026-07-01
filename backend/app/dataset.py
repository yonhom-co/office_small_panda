"""数据集管理 —— 文件接入与统一元数据。

上传 CSV/Excel → 解析为 DataFrame → 落盘 parquet（供沙箱子进程读取）
+ 生成元数据（字段/类型/采样/统计摘要）存于 shared。

数据帧不通过进程内传递，而通过工作目录的 parquet 文件，原因：
沙箱在受限子进程执行，需文件级共享；多工具（run_code/make_chart）都要读同一份数据。
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pandas as pd

# 每个会话一个工作目录；默认放系统临时目录，可由 env 覆盖
WORKDIR = Path(os.getenv("RACCOON_WORKDIR", tempfile.gettempdir())) / "raccoon_workdir"
WORKDIR.mkdir(parents=True, exist_ok=True)


def load_file(path: str | Path, name: str | None = None) -> tuple[pd.DataFrame, str]:
    """加载 CSV/Excel 为 DataFrame，返回 (df, display_name)。

    性能（阶段6 步骤5）：大文件（> LARGE_FILE_ROWS 行）先采样前 N 行做元数据探查，
    完整数据仍落 parquet 供沙箱按需读取，避免一次性撑爆内存。
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)
    return df, name or path.stem


def save_dataset(df: pd.DataFrame, name: str) -> Path:
    """落盘 DataFrame 为 parquet，返回路径。"""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    p = WORKDIR / f"{safe}.parquet"
    df.to_parquet(p, index=False)
    return p


def dataset_meta(df: pd.DataFrame, name: str, path: Path) -> dict:
    """生成统一元数据：行列数、字段类型、采样、统计摘要。"""
    import pandas as pd  # noqa: F811

    cols = []
    for col in df.columns:
        s = df[col]
        col_info = {
            "name": str(col),
            "dtype": str(s.dtype),
            "non_null": int(s.notna().sum()),
            "null": int(s.isna().sum()),
            "sample": [None if pd.isna(v) else (v.item() if hasattr(v, "item") else v)
                       for v in s.head(3).tolist()],
        }
        if pd.api.types.is_numeric_dtype(s):
            col_info.update({
                "min": None if s.dropna().empty else float(s.min()),
                "max": None if s.dropna().empty else float(s.max()),
                "mean": None if s.dropna().empty else float(s.mean()),
            })
        cols.append(col_info)
    return {
        "name": name,
        "path": str(path),
        "rows": int(len(df)),
        "cols": int(df.shape[1]),
        "columns": cols,
    }


def meta_to_text(meta: dict) -> str:
    """把元数据渲染为给 LLM 看的简洁文本。"""
    lines = [
        f"数据集：{meta['name']}（{meta['rows']} 行 × {meta['cols']} 列）",
        f"文件路径（沙箱中可用 df = pd.read_parquet 此路径）：{meta['path']}",
        "字段：",
    ]
    for c in meta["columns"]:
        extra = ""
        if "min" in c:
            extra = f" | 范围 [{c['min']}, {c['max']}] 均值 {c.get('mean')}"
        lines.append(
            f"  - {c['name']} ({c['dtype']})，非空 {c['non_null']}，空 {c['null']}{extra}"
            f" | 样例 {c['sample']}"
        )
    return "\n".join(lines)


def ingest(path: str | Path, shared: dict, name: str | None = None) -> dict:
    """端到端：加载 → 落盘 → 元数据 → 存入 shared。返回元数据。"""
    df, disp = load_file(path, name)
    parquet = save_dataset(df, disp)
    meta = dataset_meta(df, disp, parquet)
    shared.setdefault("datasets", {})[disp] = meta
    shared["current_dataset"] = disp
    return meta
