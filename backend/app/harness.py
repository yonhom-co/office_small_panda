"""Agent Harness —— Claude Code 式 tool-use 循环内核。

用 PocketFlow 的图原语实现"单节点自环"：
  AgentNode.post 依 LLM 响应决定 action：
    - stop_reason == "tool_use" → 执行工具、回灌 tool_result → 返回 "continue"（自环）
    - stop_reason == "end_turn"  → 返回 "done"（退出循环）
    - 达到步数上限            → 返回 "done"

循环步数、工具调用记录均写入 shared，支持「可追溯」。
"""
from __future__ import annotations

from typing import Any

from pocketflow import Node

from .llm import chat
from .tools import ToolRegistry, default_registry

# shared 约定键
K_MESSAGES = "messages"          # LLM 对话历史（Anthropic messages 格式）
K_TODO = "todos"                 # Todo 自管理清单
K_TRACE = "trace"                # 工具调用追溯记录
K_STEP = "step"                  # 当前循环步数
K_MAX_STEPS = "max_steps"        # 步数上限
K_TOOLS = "tools"                # ToolRegistry 实例
K_SYSTEM = "system"              # 系统提示
K_RESULT = "result"              # 最终输出文本
K_MODEL = "model"                # 使用的模型


SYSTEM_PROMPT = """你是办公小浣熊 Raccoon，一个 AI 数据分析助手。

工作方式（tool-use 循环，请高效，避免浪费步数）：
1. 先用 todo 一次性列出 3-5 个任务清单（单次调用 add 多个，之后不要每步都改 todo）。
2. 用 read_data_meta 了解数据结构。
3. 用 run_code 在沙箱执行 Python（pandas/sklearn/matplotlib/plotly 已预装，df 已加载）。
   尽量在单次 run_code 内完成一个完整分析步骤（分析+画图+打印结论），
   把多个相关计算合并到一段代码，减少调用次数。
   画图用 plt.savefig(文件名) 或 fig.write_image(文件名) 即可，会自动保存。
4. 分析充分后，用 export_report 生成 HTML 报告（传 title/summary/sections）。
5. 报告生成后，用一段话简述核心发现并结束。

规则：
- 不要臆造数据，基于 read_data_meta 与 run_code 的真实结果作答。
- 不要重复调用相同工具做相同事。
- 步数有限，聚焦完成分析与报告，少做无谓的 todo 更新。
"""


class AgentNode(Node):
    """单节点自环 tool-use 循环。"""

    def prep(self, shared: dict) -> dict:
        shared.setdefault(K_MESSAGES, [])
        shared.setdefault(K_TRACE, [])
        shared.setdefault(K_TODO, [])
        shared.setdefault(K_STEP, 0)
        shared.setdefault(K_MAX_STEPS, 12)
        shared.setdefault(K_TOOLS, default_registry)
        shared.setdefault(K_SYSTEM, SYSTEM_PROMPT)
        return {
            "messages": shared[K_MESSAGES],
            "tools": shared[K_TOOLS],
            "system": shared[K_SYSTEM],
            "model": shared.get(K_MODEL),
        }

    def exec(self, prep_res: dict) -> Any:
        registry: ToolRegistry = prep_res["tools"]
        model = prep_res["model"] or None
        resp = chat(
            model=model,
            system=prep_res["system"],
            messages=prep_res["messages"],
            tools=registry.schemas() or None,
        )
        return resp

    def post(self, shared: dict, prep_res: dict, exec_res: Any) -> str:
        resp = exec_res
        shared[K_STEP] += 1
        registry: ToolRegistry = prep_res["tools"]

        # 把 assistant 的本轮内容块原样追加到历史
        shared[K_MESSAGES].append({"role": "assistant", "content": resp.content})

        # 提取并展示思考/文本（便于追溯）
        text_parts, tool_uses = [], []
        for block in resp.content:
            btype = getattr(block, "type", None)
            if btype == "text":
                txt = getattr(block, "text", "") or ""
                if txt.strip():
                    text_parts.append(txt)
            elif btype == "tool_use":
                tool_uses.append(block)

        # 步数上限保护
        if shared[K_STEP] >= shared[K_MAX_STEPS]:
            shared[K_RESULT] = "\n".join(text_parts) or "[达到步数上限，循环终止]"
            _log(shared, "max_steps_reached", {"step": shared[K_STEP]})
            return "done"

        if resp.stop_reason == "tool_use" and tool_uses:
            # 执行所有 tool_use 块，回灌 tool_result
            tool_results = []
            for tu in tool_uses:
                params = dict(tu.input) if tu.input else {}
                out = registry.call(tu.name, params, shared)
                _log(shared, tu.name, {"input": params, "output": out})
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": out,
                    }
                )
            shared[K_MESSAGES].append({"role": "user", "content": tool_results})
            return "continue"

        # end_turn / 其他 → 完成
        shared[K_RESULT] = "\n".join(text_parts) or "[完成]"
        _log(shared, "end_turn", {})
        return "done"


def _log(shared: dict, name: str, payload: dict) -> None:
    """记录工具调用/事件到 shared[K_TRACE]，供可追溯回看。"""
    shared[K_TRACE].append({"step": shared.get(K_STEP, 0), "name": name, **payload})


def build_flow():
    """构建单节点自环 Flow：AgentNode -continue-> 自身，-done-> 结束。"""
    from pocketflow import Flow

    agent = AgentNode(max_retries=2, wait=1)
    agent - "continue" >> agent  # 自环
    return Flow(start=agent)
