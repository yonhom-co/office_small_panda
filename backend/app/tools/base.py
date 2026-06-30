"""工具注册表 —— Claude Code 式 Agent 的能力暴露层。

每个工具是一个 Tool 实例：name / description / input_schema（Anthropic 原生 tool schema）
+ executor（同步可调用）。ToolRegistry 负责注册、按名分发、导出给 LLM 的 schema 列表。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    executor: Callable[[dict[str, Any], dict], Any]
    # executor 签名：(params, shared) -> result（result 会被 JSON 序列化回灌给 LLM）

    def to_schema(self) -> dict[str, Any]:
        """导出为 Anthropic messages.create 的 tools 入参格式。"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def run(self, params: dict[str, Any], shared: dict) -> str:
        """执行工具，返回字符串形式的结果（供回灌上下文）。"""
        try:
            result = self.executor(params, shared)
        except Exception as e:  # 工具失败不应击垮 harness
            return f"[工具 {self.name} 执行出错] {type(e).__name__}: {e}"
        return _stringify(result)


def _stringify(result: Any) -> str:
    if isinstance(result, str):
        return result
    import json

    try:
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception:
        return str(result)


class ToolRegistry:
    """工具注册与分发。"""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"工具已注册: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def schemas(self) -> list[dict[str, Any]]:
        return [t.to_schema() for t in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def call(self, name: str, params: dict[str, Any], shared: dict) -> str:
        tool = self.get(name)
        if tool is None:
            return f"[未知工具] {name}；可用工具：{self.names()}"
        return tool.run(params, shared)


# 默认全局注册表
default_registry = ToolRegistry()
