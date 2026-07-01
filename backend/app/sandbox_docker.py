"""Docker 沙箱 —— 强隔离执行 LLM 生成的 Python（补齐阶段5 步骤6）。

安全策略：
- 容器隔离（独立文件系统/进程/网络命名空间）
- --network none：禁网
- --memory / --cpus：资源限额
- --read-only：只读根文件系统（仅挂载数据/charts 目录可写）
- 超时回收
- 镜像预装数据分析库（pandas/sklearn/matplotlib/plotly），白名单由镜像固化

需 Docker daemon 可用。不可用时降级回子进程沙箱（sandbox.py），如实标注。

镜像构建：docker build -t raccoon-sandbox deploy/sandbox/
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

from .dataset import WORKDIR

TIMEOUT = int(os.getenv("RACCOON_SANDBOX_TIMEOUT", "60"))
SANDBOX_IMAGE = os.getenv("SANDBOX_IMAGE", "raccoon-sandbox:latest")

# 复用子进程沙箱的 runner 脚本（预加载 + 图表劫持逻辑一致）
from .sandbox import _RUNNER  # noqa: E402


def docker_available() -> bool:
    """Docker daemon 是否可用。"""
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def run_code_docker(code: str, parquet_path: str | None, timeout: int = TIMEOUT) -> dict:
    """在 Docker 容器中执行 code，强隔离。"""
    charts_dir = WORKDIR / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    before = set(p.name for p in charts_dir.glob("*.png"))

    full_code = textwrap.dedent(f"""
        import os
        _CHARTS_DIR = {str(charts_dir)!r}
        def _save_fig(fig=None, name=None):
            import matplotlib.pyplot as plt
            name = name or ("chart_"+str(len(os.listdir(_CHARTS_DIR))))
            path = os.path.join(_CHARTS_DIR, name+".png")
            (fig or plt.gcf()).savefig(path, dpi=100, bbox_inches="tight")
            print(f"[chart saved] {{path}}"); return path
        def _save_plotly(fig, name=None):
            name = name or ("chart_"+str(len(os.listdir(_CHARTS_DIR))))
            path = os.path.join(_CHARTS_DIR, name+".png")
            fig.write_image(path, scale=1); print(f"[chart saved] {{path}}"); return path
        os.chdir({str(WORKDIR)!r})
    """) + "\n" + code

    script = _RUNNER.format(
        allowed=repr({"pandas","pd","numpy","np","sklearn","scipy","matplotlib","mpl",
                      "plotly","express","px","graph_objects","go","datetime","math",
                      "statistics","json","re","os","sys","io","time","itertools",
                      "collections","functools","pathlib","warnings","numbers","decimal",
                      "fractions","operator","copy","hashlib","base64","csv","textwrap",
                      "typing","dateutil","pytz","tzdata","pyparsing","cycler","kiwisolver",
                      "fonttools","contourpy","packaging","six","pillow","PIL",
                      "charset_normalizer","platformdirs"}),
        blocked=repr({"socket","subprocess","multiprocessing","http","urllib","requests",
                      "ftplib","telnetlib","smtplib","ssl"}),
        parquet_path=parquet_path,
        code=full_code,
    )

    # 写脚本到工作目录挂载进容器
    script_path = WORKDIR / "_sandbox_runner.py"
    script_path.write_text(script, encoding="utf-8")

    try:
        proc = subprocess.run(
            [
                "docker", "run", "--rm",
                "--network", "none",              # 禁网
                "--memory", "512m",                # 内存限额
                "--cpus", "1.0",                   # CPU 限额
                "--read-only",                     # 只读根
                "--tmpfs", "/tmp:rw,size=64m",     # 临时目录可写
                "-v", f"{WORKDIR}:{WORKDIR}",       # 挂载工作目录（含数据/charts）
                "-e", "MPLBACKEND=Agg",
                SANDBOX_IMAGE,
                "python", str(script_path),
            ],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"stdout": "", "error": f"[Docker 沙箱超时] 超过 {timeout}s", "charts": []}

    out = proc.stdout
    marker = "<<<SANDBOX_RESULT>>>"
    stdout_part, result_json = out, {}
    if marker in out:
        stdout_part, _, result_str = out.partition(marker)
        try:
            result_json = json.loads(result_str.strip())
        except json.JSONDecodeError:
            result_json = {"error": "沙箱结果解析失败"}

    new_charts = sorted(str(charts_dir / n)
                        for n in (set(p.name for p in charts_dir.glob("*.png")) - before))
    return {
        "stdout": stdout_part + result_json.get("stdout", ""),
        "error": result_json.get("error") or (proc.stderr if proc.returncode else None),
        "charts": new_charts,
    }


def run_code_isolated(code: str, parquet_path: str | None, timeout: int = TIMEOUT) -> dict:
    """优先 Docker 强隔离；daemon 不可用时降级子进程。"""
    if docker_available():
        return run_code_docker(code, parquet_path, timeout)
    # 降级：子进程（阶段1 方案）
    from .sandbox import run_code as _run_subprocess
    return _run_subprocess(code, parquet_path, timeout)
