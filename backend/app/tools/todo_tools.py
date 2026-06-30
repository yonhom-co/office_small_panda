"""todo 工具 —— Agent 自管理任务清单（复刻「任务规划/可追溯」雏形）。

模型用本工具维护一个待办清单：列出步骤、勾选完成。清单存于 shared，可追溯。
"""
from __future__ import annotations

from .base import Tool, default_registry


def _todo(params: dict, shared: dict) -> str:
    action = params.get("action", "list")
    todos: list = shared.setdefault("todos", [])

    if action == "add":
        item = {"content": params["content"], "status": "pending"}
        todos.append(item)
        return f"已添加待办（共 {len(todos)} 项）：{params['content']}"
    if action == "done":
        idx = params["index"] - 1
        if 0 <= idx < len(todos):
            todos[idx]["status"] = "done"
            return f"已完成：{todos[idx]['content']}"
        return f"无效序号：{params['index']}"
    if action == "update":
        idx = params["index"] - 1
        if 0 <= idx < len(todos):
            todos[idx]["content"] = params["content"]
            return f"已更新第 {params['index']} 项"
        return f"无效序号：{params['index']}"
    # list
    if not todos:
        return "（当前无待办）"
    lines = ["当前待办清单："]
    for i, t in enumerate(todos, 1):
        mark = "✓" if t["status"] == "done" else "○"
        lines.append(f"  {i}. [{mark}] {t['content']}")
    return "\n".join(lines)


todo_tool = Tool(
    name="todo",
    description="管理任务清单：add（新增，传 content）、done（标记完成，传 index）、update（修改，传 index/content）、list（查看）。先 add 列出步骤，完成一项就 done。",
    input_schema={
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["add", "done", "update", "list"]},
            "content": {"type": "string", "description": "add/update 时的内容"},
            "index": {"type": "integer", "description": "done/update 的序号（从1开始）"},
        },
        "required": ["action"],
    },
    executor=_todo,
)

default_registry.register(todo_tool)
