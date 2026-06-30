"""LLM 客户端封装。

主用火山方舟编程套餐（coding plan）的 Anthropic 兼容端点，原生 tool use。
端点：base_url + /v1/messages
鉴权：Authorization: Bearer <key>（anthropic SDK 用 auth_token 即可）。

实测（2026-06-30）：
- /v1/messages 返回标准 Anthropic Messages 响应，stop_reason=tool_use 时含 tool_use 块。
- glm-5.2 / deepseek-v4-pro 支持 thinking 内容块（扩展思考）。
- 报 UnsupportedModel 的模型不在 coding plan 放行列表，需从 .env 选用白名单模型。
"""
import os

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

client = Anthropic(
    base_url=os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/coding"),
    auth_token=os.getenv("ARK_API_KEY"),
)

MODEL = os.getenv("ARK_MODEL", "glm-5.2")
MAX_TOKENS = int(os.getenv("ARK_MAX_TOKENS", "8192"))

# 按用途选型（coding plan 网关白名单内的模型）
MODEL_PLAN = os.getenv("ARK_MODEL_PLAN", MODEL)          # 规划/深度思考
MODEL_REASON = os.getenv("ARK_MODEL_REASON", MODEL)      # 数据分析子代理
MODEL_CODE = os.getenv("ARK_MODEL_CODE", MODEL)          # 沙箱代码生成
MODEL_LITE = os.getenv("ARK_MODEL_LITE", MODEL)          # 轻任务/路由/Todo


def chat(messages, *, model=MODEL, tools=None, max_tokens=MAX_TOKENS, **kw):
    """同步调用 messages.create，返回原始响应。

    tool-use 循环由调用方（PocketFlow AgentNode）驱动：
    resp.stop_reason == "tool_use" → 取 tool_use 块执行 → 回灌 tool_result → 继续。
    resp.stop_reason == "end_turn" → 任务完成。
    """
    return client.messages.create(
        model=model or MODEL,
        max_tokens=max_tokens,
        tools=tools,
        messages=messages,
        **kw,
    )


def chat_stream(messages, *, model=MODEL, tools=None, max_tokens=MAX_TOKENS,
                on_text=None, on_event=None, **kw):
    """流式调用 messages.create，返回聚合后的完整响应。

    on_text(chunk: str)：文本增量回调（每个 text delta 调用一次）。
    on_event(event: dict)：事件回调，如 {"type":"tool_use","name":...,"input":...}、
                          {"type":"step","stop_reason":...} 等，供 SSE/前端推送。
    流式与 tool use 兼容：Anthropic 流式响应会在末尾聚合为完整 Message，
    含 stop_reason 与 tool_use 块，调用方处理方式与非流式一致。
    """
    on_text = on_text or (lambda c: None)
    on_event = on_event or (lambda e: None)
    with client.messages.stream(
        model=model or MODEL,
        max_tokens=max_tokens,
        tools=tools,
        messages=messages,
        **kw,
    ) as stream:
        for chunk_text in stream.text_stream:
            if chunk_text:
                on_text(chunk_text)
        resp = stream.get_final_message()
    on_event({"type": "message_done", "stop_reason": resp.stop_reason})
    return resp
