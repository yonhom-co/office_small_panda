"""多租户与权限（补齐阶段5 步骤5）。

模型：Tenant → User → Role；会话归属租户；数据（数据集/知识库/产物）按租户隔离；
工具白名单按角色控制；操作审计（复用 hooks audit.log）。

角色：
- admin：全部工具，可管理租户
- analyst：数据分析相关工具（无 gen_ppt? 含）
- viewer：只读（read_data_meta/query_kb/export_report 下载）

权限以"工具白名单"形式落地：harness 启动时按角色过滤工具注册表。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 角色工具白名单（None 表示全部允许）
ROLE_TOOLS: dict[str, set[str] | None] = {
    "admin": None,  # 全部
    "analyst": {"upload_data", "read_data_meta", "run_code", "make_chart",
                "todo", "export_report", "dispatch_subagent", "plan", "call_mcp"},
    "viewer": {"read_data_meta", "query_kb", "export_report"},
}


@dataclass
class User:
    uid: str
    name: str
    tenant: str
    role: str = "analyst"
    allowed_tools: set[str] | None = field(default=None)

    def can(self, tool_name: str) -> bool:
        allowed = self.allowed_tools if self.allowed_tools is not None else ROLE_TOOLS.get(self.role)
        return allowed is None or tool_name in allowed


# 内存用户库（阶段5 持久化前用内存；admin/analyst/viewer 示例）
_USERS: dict[str, User] = {
    "admin1": User("admin1", "管理员", tenant="org_a", role="admin"),
    "analyst1": User("analyst1", "数据分析师", tenant="org_a", role="analyst"),
    "viewer1": User("viewer1", "查看者", tenant="org_b", role="viewer"),
}


def get_user(uid: str) -> User | None:
    return _USERS.get(uid)


def list_users() -> list[dict]:
    return [{"uid": u.uid, "name": u.name, "tenant": u.tenant, "role": u.role} for u in _USERS.values()]


def tenant_scope(shared: dict, user: User) -> dict:
    """给 shared 打租户标签，用于数据隔离。"""
    shared["tenant"] = user.tenant
    shared["user"] = user.uid
    shared["role"] = user.role
    return shared


def filtered_tools(user: User, registry) -> Any:
    """返回按角色过滤后的工具注册表（受限副本）。"""
    from .tools import ToolRegistry
    allowed = user.allowed_tools if user.allowed_tools is not None else ROLE_TOOLS.get(user.role)
    if allowed is None:
        return registry
    sub = ToolRegistry()
    for name in allowed:
        t = registry.get(name)
        if t:
            sub.register(t)
    return sub
