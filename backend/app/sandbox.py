"""代码沙箱 —— 隔离执行 LLM 生成的 Python。

MVP 安全策略（子进程 + 预加载）：
- 在独立 Python 子进程中执行，与主进程隔离。
- 预先把数据分析库（pandas/numpy/matplotlib/sklearn/plotly）import 进 globals，
  用户代码在其中 exec；不再用 import 钩子（pandas 3.x import 期需 subprocess/locale，
  钩子方案与之冲突）。
- 超时：硬中止子进程。
- 网络隔离：数据分析代码不主动连网；超时 + 子进程隔离提供基本边界。
  更强隔离（禁网命名空间 / Firecracker microVM）留待阶段 5。
- 图表：约定代码用 _save_fig() / _save_plotly() 保存到 charts 目录。

设计权衡见报告 §2.4「诚实付出的代价」与 §6 风险对策。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap

from .dataset import WORKDIR

TIMEOUT = int(os.getenv("RACCOON_SANDBOX_TIMEOUT", "60"))

# 子进程执行的包装脚本：预加载库 + 受限 globals + 捕获输出
_RUNNER = textwrap.dedent('''
import sys, json, io, traceback, contextlib, os

# 预加载数据科学库（这些是数据分析所需，预先 import 避免 import 钩子冲突）
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import sklearn
import plotly.express as px
import plotly.graph_objects as go

# 加载数据（若提供）
df = None
if {parquet_path!r}:
    df = pd.read_parquet({parquet_path!r})

# 图表保存辅助
_CHARTS_DIR = {charts_dir!r}
os.makedirs(_CHARTS_DIR, exist_ok=True)

def _safe_name(name, ext="png"):
    import re as _re
    base = _re.sub(r"[^0-9A-Za-z一-鿿_-]", "_", str(name or "chart"))
    return os.path.join(_CHARTS_DIR, base + "." + ext)

def _save_fig(fig=None, name=None):
    import matplotlib.pyplot as plt
    name = name or ("chart_" + str(len(os.listdir(_CHARTS_DIR))))
    path = _safe_name(name)
    (fig or plt.gcf()).savefig(path, dpi=100, bbox_inches="tight")
    print(f"[chart saved] {{path}}")
    return path
def _save_plotly(fig, name=None):
    name = name or ("chart_" + str(len(os.listdir(_CHARTS_DIR))))
    path = _safe_name(name)
    fig.write_image(path, scale=1)
    print(f"[chart saved] {{path}}")
    return path

# 劫持 matplotlib savefig 与 plotly write_image：无论 Agent 用什么文件名，
# 一律重定向到 charts 目录，确保产出可被收集。
import matplotlib.figure
_orig_savefig = matplotlib.figure.Figure.savefig
def _patched_savefig(self, fname, *a, **k):
    fname = _safe_name(fname if isinstance(fname, str) else None)
    return _orig_savefig(self, fname, *a, **k)
matplotlib.figure.Figure.savefig = _patched_savefig

_orig_write_image = go.Figure.write_image
def _patched_write_image(self, fname, *a, **k):
    fname = _safe_name(fname if isinstance(fname, str) else None)
    return _orig_write_image(self, fname, *a, **k)
go.Figure.write_image = _patched_write_image

os.chdir({workdir!r})

# 受限 globals：暴露预加载的库与数据，禁用 open 的写能力外的危险项
_safe_globals = {{
    "__name__": "__sandbox__", "__builtins__": __builtins__,
    "pd": pd, "np": np, "plt": plt, "matplotlib": matplotlib,
    "sklearn": sklearn, "px": px, "go": go, "df": df,
    "_save_fig": _save_fig, "_save_plotly": _save_plotly,
    "print": print, "len": len, "range": range, "enumerate": enumerate,
    "zip": zip, "sorted": sorted, "sum": sum, "min": min, "max": max,
    "abs": abs, "round": round, "list": list, "dict": dict, "set": set,
    "tuple": tuple, "str": str, "int": int, "float": float, "bool": bool,
    "type": type, "isinstance": isinstance, "enumerate": enumerate,
}}

_out = io.StringIO()
_err = None
try:
    with contextlib.redirect_stdout(_out):
        exec(compile({code!r}, "<sandbox>", "exec"), _safe_globals)
except Exception:
    _err = traceback.format_exc()

print("<<<SANDBOX_RESULT>>>")
print(json.dumps({{"stdout": _out.getvalue(), "error": _err}}, ensure_ascii=False, default=str))
''')


def run_code(code: str, parquet_path: str | None, timeout: int = TIMEOUT) -> dict:
    """在子进程中执行 code，返回 {stdout, error, charts}。"""
    charts_dir = WORKDIR / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    # 记录执行前的图表，便于识别本次新增
    before = set(p.name for p in charts_dir.glob("*.png"))

    script = _RUNNER.format(
        parquet_path=parquet_path,
        charts_dir=str(charts_dir),
        workdir=str(WORKDIR),
        code=code,
    )

    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "MPLBACKEND": "Agg"},
        )
    except subprocess.TimeoutExpired:
        return {"stdout": "", "error": f"[沙箱超时] 超过 {timeout}s 被中止", "charts": []}

    out = proc.stdout
    marker = "<<<SANDBOX_RESULT>>>"
    stdout_part = out
    result_json = {}
    if marker in out:
        stdout_part, _, result_str = out.partition(marker)
        try:
            result_json = json.loads(result_str.strip())
        except json.JSONDecodeError:
            result_json = {"error": "沙箱结果解析失败"}

    new_charts = sorted(str(charts_dir / n) for n in (set(p.name for p in charts_dir.glob("*.png")) - before))
    return {
        "stdout": stdout_part + result_json.get("stdout", ""),
        "error": result_json.get("error") or (proc.stderr if proc.returncode else None),
        "charts": new_charts,
    }
