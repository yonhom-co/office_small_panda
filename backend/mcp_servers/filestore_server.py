"""示例 MCP Server —— 模拟企业内部数据源（文件存储连接器）。

作为 MCP（Model Context Protocol）server，通过 stdio 与 client 通信，
暴露 list_files / read_file 工具。Agent 经 MCP client 调用，接入外部数据。

运行（由 client 拉起）：python filestore_server.py
真实场景可替换为 ERP/CRM/OA 连接器，实现相同 MCP 接口。
"""
from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# 模拟企业数据目录（可用 env 覆盖为真实数据源路径）
DATA_DIR = Path(os.getenv("MCP_FILESTORE_DIR", "data/mcp_filestore"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

mcp = FastMCP("filestore")


@mcp.tool()
def list_files() -> list[str]:
    """列出数据源中所有文件。"""
    return [p.name for p in DATA_DIR.iterdir() if p.is_file()]


@mcp.tool()
def read_file(name: str) -> str:
    """读取指定文件内容。"""
    p = DATA_DIR / name
    if not p.exists() or not p.is_file():
        return f"[文件不存在] {name}"
    return p.read_text(encoding="utf-8", errors="ignore")


if __name__ == "__main__":
    mcp.run()
