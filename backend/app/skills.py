"""Skills 机制 —— 按需加载能力包（Claude Code 式）。

每个 Skill 是一个 Markdown 指令包：
- name：触发名（@name）
- description：何时使用
- instructions：载入系统提示的指令文本
- tools：推荐工具集（可选，仅提示模型，不强制限制）

平时不占上下文；@name 触发或 load_skill 工具调用时才载入。
本阶段实现框架；行业包（教育/医疗/电商/采购/财务）在阶段 6 填充。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Skill:
    name: str
    description: str
    instructions: str
    tools: list[str] = field(default_factory=list)

    def to_prompt(self) -> str:
        """渲染为载入系统提示的文本。"""
        parts = [f"【Skill: {self.name}】", self.instructions]
        if self.tools:
            parts.append("推荐工具：" + ", ".join(self.tools))
        return "\n".join(parts)


# 内置 Skills 目录（Markdown 文件，frontmatter + 指令正文）
SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"


def _parse_skill_md(path: Path) -> Skill | None:
    """解析 Skill Markdown 文件：frontmatter（name/description/triggers/tools/report_style）+ 正文指令。"""
    import re
    text = path.read_text(encoding="utf-8")
    # frontmatter
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        return None
    fm_raw, body = m.group(1), m.group(2).strip()
    fm: dict = {}
    for line in fm_raw.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                v = [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
            fm[k.strip()] = v
    name = fm.get("name", path.stem)
    tools_raw = fm.get("tools", [])
    if isinstance(tools_raw, str):
        tools_raw = [t.strip() for t in tools_raw.split(",") if t.strip()]
    return Skill(
        name=name,
        description=fm.get("description", ""),
        instructions=body or f"载入 Skill: {name}",
        tools=list(tools_raw),
    )


class SkillRegistry:
    """Skill 注册与按需加载。"""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill

    def load_from_dir(self, dir_path: Path) -> None:
        """从目录加载所有 .md Skill 文件。"""
        if not dir_path.exists():
            return
        for md in sorted(dir_path.glob("*.md")):
            skill = _parse_skill_md(md)
            if skill:
                self.register(skill)

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def names(self) -> list[str]:
        return list(self._skills.keys())

    def load(self, name: str) -> str:
        """载入 Skill，返回其指令文本（注入系统提示）。"""
        skill = self.get(name)
        if skill is None:
            available = self.names()
            return f"[未知 Skill] {name}；可用：{available}"
        return skill.to_prompt()


default_skills = SkillRegistry()
# 注册内置 writing Skill（代码定义）
default_skills.register(Skill(
    name="writing",
    description="文案创作：邮件、海报、通用文案",
    instructions=(
        "进入文案创作模式。要求：\n"
        "- 先确认文案类型（邮件/海报/文案）、目标读者、核心信息。\n"
        "- 文案需贴合场景语气，结构清晰（如邮件：称呼/正文/落款）。\n"
        "- 若提供了知识库上下文（@知识库），务必基于其中真实内容，引用关键事实。"
    ),
    tools=["query_kb", "todo"],
))
# 从 skills/ 目录加载行业 Skill 包（教育/医疗/电商/采购/财务）
default_skills.load_from_dir(SKILLS_DIR)


def load_skill_prompt(name: str) -> str:
    """供 load_skill 工具与 @触发 调用。"""
    return default_skills.load(name)


def load_skill_prompt(name: str) -> str:
    """供 load_skill 工具与 @触发 调用。"""
    return default_skills.load(name)
