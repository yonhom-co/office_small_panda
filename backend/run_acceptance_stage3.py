"""阶段 3 端到端验收脚本。

场景：
  1. 上传公司介绍文档到知识库「公司介绍」
  2. 输入"基于 @公司介绍 写一封商务合作邮件"
  3. @触发：解析到知识库 → 检索相关片段注入；writing Skill 也可触发
  4. Agent 产出引用原文的邮件
  5. 验证 @能力 能触发 Skill 载入

用法：.venv/bin/python backend/run_acceptance_stage3.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.knowledge_base import ingest_document, query_kb  # noqa: E402
from app.skills import default_skills, load_skill_prompt  # noqa: E402
from app.at_trigger import resolve_mentions, parse_at_mentions  # noqa: E402
from app.harness import build_flow  # noqa: E402
import app.tools_registry  # noqa: E402,F401


SAMPLE_DOC = Path(__file__).resolve().parent.parent / "data" / "company_intro.txt"


def ensure_sample_doc() -> Path:
    """若不存在则生成一份示例公司介绍文档。"""
    if SAMPLE_DOC.exists():
        return SAMPLE_DOC
    SAMPLE_DOC.parent.mkdir(parents=True, exist_ok=True)
    SAMPLE_DOC.write_text(
        "商汤智能办公助手——办公小浣熊 Raccoon 产品介绍\n"
        "办公小浣熊是商汤科技基于日日新大模型打造的 AI 智能办公助手，"
        "提供一站式创作平台和知识管理空间。核心能力包括数据分析、报告生成、PPT 制作、"
        "文案创作与专属知识库。\n"
        "商务合作联系方式：商务邮箱 business@example.com，合作热线 010-8888-8888。"
        "公司总部位于北京，可提供私有化部署与软硬一体机方案。",
        encoding="utf-8")
    return SAMPLE_DOC


def main() -> dict:
    doc = ensure_sample_doc()
    print(f"=== 1. 上传文档到知识库「公司介绍」===\n文件: {doc.name}")

    # 1. ingestion（需 embedding，首次加载模型较慢）
    info = ingest_document(str(doc), kb="公司介绍")
    print(f"入库：{info['chunks']} 片段，{info['chars']} 字符\n")

    # 2. 检索验证
    print("=== 2. 检索验证 ===")
    hits = query_kb("公司介绍", "商务合作联系方式是什么", top_k=2)
    for h in hits:
        print(f"  来源 {h['source']}：{h['text'][:80]}...")
    print()

    # 3. @触发解析验证
    user_msg = "基于 @公司介绍 写一封商务合作邮件"
    print(f"=== 3. @触发解析 ===\n用户: {user_msg}")
    print("@提及:", parse_at_mentions(user_msg))
    shared = {"messages": [{"role": "user", "content": user_msg}], "max_steps": 10}
    injection = resolve_mentions(user_msg, shared)
    print("注入内容预览:", injection[:200], "...\n")

    # 4. Skill 触发验证
    print("=== 4. @writing Skill 触发 ===")
    print(load_skill_prompt("writing")[:80], "...\n")

    # 5. Agent 产出邮件
    print("=== 5. Agent 产出邮件 ===")
    shared["messages"] = [{"role": "user", "content": user_msg}]
    flow = build_flow()
    flow.run(shared)
    print("\n【最终回复】")
    print(shared.get("result", "(空)"))
    print("\n【使用的知识库】", shared.get("kb_used", []))
    print("【加载的 Skill】", shared.get("loaded_skills", []))
    print("【工具调用追溯】", [t["name"] for t in shared.get("trace", [])])
    return shared


if __name__ == "__main__":
    main()
