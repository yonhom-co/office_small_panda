"""MCP Client —— 连接 MCP server，列工具、调工具（补齐阶段5 步骤1）。

Agent 通过 call_mcp 工具调用外部数据源（ERP/CRM/OA/内部知识库），
无需改内核。MCP server 作为子进程由 client 拉起，stdio 通信。

注册的 server 在 MCP_SERVERS 字典配置（命令 + 参数）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# MCP server 注册表：name → (command, args, env)
MCP_SERVERS: dict[str, dict] = {
    "filestore": {
        "command": sys.executable,  # 用当前 venv python（已装 mcp）
        "args": [str(Path(__file__).resolve().parent.parent / "mcp_servers" / "filestore_server.py")],
        "env": {},
    },
}

def _build_params(name: str):
    """构造某 server 的 StdioServerParameters。"""
    from mcp import StdioServerParameters
    spec = MCP_SERVERS.get(name)
    if not spec:
        raise ValueError(f"未知 MCP server: {name}；可用: {list(MCP_SERVERS.keys())}")
    env = {**os.environ, **spec.get("env", {})}
    return StdioServerParameters(command=spec["command"], args=spec["args"], env=env)


def call_mcp(server: str, tool: str, arguments: dict | None = None) -> str:
    """同步调用 MCP server 的工具：每次新建连接并关闭（避免跨事件循环问题）。"""
    import asyncio
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    async def _run():
        params = _build_params(server)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool, arguments or {})
                parts = []
                for c in (result.content or []):
                    txt = getattr(c, "text", None) or str(c)
                    parts.append(txt)
                return "\n".join(parts)

    try:
        return asyncio.run(_run())
    except Exception as e:
        return f"[MCP 调用失败] {type(e).__name__}: {e}"


def list_mcp_tools(server: str) -> list[str]:
    """列出某 MCP server 暴露的工具。"""
    import asyncio
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    async def _run():
        params = _build_params(server)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                return [t.name for t in tools.tools]

    try:
        return asyncio.run(_run())
    except Exception as e:
        return [f"[错误] {e}"]
