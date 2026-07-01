"""call_mcp 工具 —— Agent 通过 MCP 接入外部数据源（补齐阶段5 步骤1）。

示例：Agent 调 call_mcp(server="filestore", tool="read_file", arguments={"name":"orders.csv"})
拉取企业内部数据。ERP/CRM/OA 可实现为相同接口的 MCP server。
"""
from __future__ import annotations

from .base import Tool, default_registry
from ..mcp_client import call_mcp, list_mcp_tools, MCP_SERVERS


def _call_mcp(params: dict, shared: dict) -> str:
    server = params["server"]
    tool = params["tool"]
    arguments = params.get("arguments", {})
    if server not in MCP_SERVERS:
        return f"未知 MCP server: {server}；可用: {list(MCP_SERVERS.keys())}"
    result = call_mcp(server, tool, arguments)
    return f"[MCP {server}/{tool} 结果]\n{result}"


call_mcp_tool = Tool(
    name="call_mcp",
    description=(
        "通过 MCP（Model Context Protocol）调用外部数据源工具。"
        "传 server（如 filestore）、tool（工具名，如 read_file/list_files）、"
        "arguments（参数对象）。用于接入企业 ERP/CRM/OA/内部知识库等外部数据。"
        f"已注册 server: {list(MCP_SERVERS.keys())}"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "server": {"type": "string", "description": "MCP server 名，如 filestore"},
            "tool": {"type": "string", "description": "工具名，如 read_file"},
            "arguments": {"type": "object", "description": "工具参数"},
        },
        "required": ["server", "tool"],
    },
    executor=_call_mcp,
)

default_registry.register(call_mcp_tool)
