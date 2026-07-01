"""LLMProvider 抽象层 —— harness 与模型解耦（补齐阶段5 步骤4）。

接口：create_messages / stream_messages，返回 Anthropic 兼容的 Message 对象
（含 content / stop_reason / usage），harness 处理方式统一。

实现：
- ArkAnthropicProvider：火山引擎 ARK coding plan Anthropic 兼容端点（默认）。
- VLLMProvider：本地 vLLM 的 OpenAI 兼容端点，转译为 Anthropic Message 形态
  （私有化用；tool use 经转译，文本/thinking 仍可用）。

通过环境变量 LLM_PROVIDER 切换（ark / vllm）。
"""
from __future__ import annotations

import os
from typing import Any, Callable

from dotenv import load_dotenv

load_dotenv()

PROVIDER = os.getenv("LLM_PROVIDER", "ark").lower()


class LLMProvider:
    """抽象接口。子类实现 create_messages / stream_messages。"""

    name = "base"

    def create_messages(self, *, model, messages, tools=None, max_tokens=8192, system=None, **kw) -> Any:
        raise NotImplementedError

    def stream_messages(self, *, model, messages, tools=None, max_tokens=8192,
                        system=None, on_text=None, on_event=None, **kw) -> Any:
        # 默认退化为非流式（子类可覆盖）
        on_event = on_event or (lambda e: None)
        resp = self.create_messages(model=model, messages=messages, tools=tools,
                                    max_tokens=max_tokens, system=system, **kw)
        on_event({"type": "message_done", "stop_reason": resp.stop_reason})
        return resp


class ArkAnthropicProvider(LLMProvider):
    """火山引擎 ARK coding plan Anthropic 兼容端点（默认）。"""

    name = "ark"

    def __init__(self) -> None:
        from anthropic import Anthropic
        self.client = Anthropic(
            base_url=os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/coding"),
            auth_token=os.getenv("ARK_API_KEY"),
        )

    def create_messages(self, *, model, messages, tools=None, max_tokens=8192, system=None, **kw) -> Any:
        return self.client.messages.create(
            model=model, max_tokens=max_tokens, tools=tools,
            messages=messages, system=system, **kw,
        )

    def stream_messages(self, *, model, messages, tools=None, max_tokens=8192,
                        system=None, on_text=None, on_event=None, **kw) -> Any:
        on_text = on_text or (lambda c: None)
        on_event = on_event or (lambda e: None)
        with self.client.messages.stream(
            model=model, max_tokens=max_tokens, tools=tools,
            messages=messages, system=system, **kw,
        ) as stream:
            for chunk in stream.text_stream:
                if chunk:
                    on_text(chunk)
            resp = stream.get_final_message()
        on_event({"type": "message_done", "stop_reason": resp.stop_reason})
        return resp


class VLLMProvider(LLMProvider):
    """本地 vLLM（OpenAI 兼容）端点 —— 私有化用。

    将 OpenAI chat/completions 响应转译为 Anthropic Message 形态，
    使 harness 无感知。tool_use 转译为 Anthropic tool_use 块。
    """

    name = "vllm"

    def __init__(self) -> None:
        from openai import OpenAI
        self.client = OpenAI(
            base_url=os.getenv("VLLM_BASE_URL", "http://localhost:8001/v1"),
            api_key=os.getenv("VLLM_API_KEY", "local"),
        )

    def create_messages(self, *, model, messages, tools=None, max_tokens=8192, system=None, **kw) -> Any:
        msgs = list(messages)
        if system:
            msgs = [{"role": "system", "content": system}] + msgs
        # OpenAI tool schema 转换（Anthropic input_schema → JSON schema parameters）
        oai_tools = None
        if tools:
            oai_tools = [{
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {"type": "object"}),
                },
            } for t in tools]
        resp = self.client.chat.completions.create(
            model=model, messages=msgs, tools=oai_tools,
            max_tokens=max_tokens, **kw,
        )
        return _openai_to_anthropic(resp)

    def stream_messages(self, *, model, messages, tools=None, max_tokens=8192,
                        system=None, on_text=None, on_event=None, **kw) -> Any:
        on_text = on_text or (lambda c: None)
        on_event = on_event or (lambda e: None)
        msgs = list(messages)
        if system:
            msgs = [{"role": "system", "content": system}] + msgs
        oai_tools = None
        if tools:
            oai_tools = [{
                "type": "function", "function": {
                    "name": t["name"], "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {"type": "object"}),
                },
            } for t in tools]
        text_buf = []
        tool_calls: dict[int, dict] = {}
        finish = None
        stream = self.client.chat.completions.create(
            model=model, messages=msgs, tools=oai_tools,
            max_tokens=max_tokens, stream=True, **kw,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                text_buf.append(delta.content)
                on_text(delta.content)
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls:
                        tool_calls[idx] = {"id": tc.id or f"call_{idx}",
                                           "name": tc.function.name, "args": ""}
                    if tc.function and tc.function.arguments:
                        tool_calls[idx]["args"] += tc.function.arguments
            if chunk.choices[0].finish_reason:
                finish = chunk.choices[0].finish_reason
        # 聚合为 Anthropic Message
        resp = _build_anthropic("".join(text_buf), list(tool_calls.values()), finish)
        on_event({"type": "message_done", "stop_reason": resp.stop_reason})
        return resp


def _openai_to_anthropic(resp) -> Any:
    """OpenAI 非流式响应 → Anthropic Message 对象。"""
    choice = resp.choices[0]
    msg = choice.message
    text = msg.content or ""
    tcs = []
    if msg.tool_calls:
        for i, tc in enumerate(msg.tool_calls):
            import json as _json
            try:
                args = _json.loads(tc.function.arguments or "{}")
            except Exception:
                args = {}
            tcs.append({"id": tc.id, "name": tc.function.name, "input": args})
    return _build_anthropic(text, tcs, choice.finish_reason, usage=resp.usage)


def _build_anthropic(text, tool_calls, finish, usage=None) -> Any:
    """构造一个 duck-typed Anthropic Message 对象（最小集，harness 只用 content/stop_reason）。"""
    content = []
    if text:
        content.append({"type": "text", "text": text})
    for tc in tool_calls:
        content.append({"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["input"]})
    stop = "tool_use" if tool_calls else "end_turn"
    if finish == "length":
        stop = "max_tokens"

    class _Block:
        def __init__(self, d): self.__dict__.update(d)
        @property
        def type(self): return self.__dict__.get("type")

    class _Msg:
        def __init__(self, content, stop_reason, usage):
            self.content = [_Block(c) for c in content]
            self.stop_reason = stop_reason
            self.usage = usage

    return _Msg(content, stop, usage)


def get_provider() -> LLMProvider:
    """按环境变量返回 provider 单例。"""
    global _provider
    if _provider is None:
        if PROVIDER == "vllm":
            _provider = VLLMProvider()
        else:
            _provider = ArkAnthropicProvider()
    return _provider


_provider: LLMProvider | None = None
