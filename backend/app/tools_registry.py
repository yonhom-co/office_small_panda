"""工具注册表加载入口 —— import 即触发各工具模块的注册。"""
from .tools import default_registry
from .tools import data_tools  # noqa: F401
from .tools import upload_tools  # noqa: F401
from .tools import sandbox_tools  # noqa: F401
from .tools import chart_tools  # noqa: F401
from .tools import todo_tools  # noqa: F401
from .tools import report_tools  # noqa: F401
from .tools import subagent_tools  # noqa: F401
from .tools import ppt_tools  # noqa: F401
from .tools import plan_tools  # noqa: F401
from .tools import skill_tools  # noqa: F401
from .tools import kb_tools  # noqa: F401
from .tools import mcp_tools  # noqa: F401

__all__ = ["default_registry"]
