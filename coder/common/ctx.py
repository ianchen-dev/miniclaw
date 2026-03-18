from contextvars import ContextVar
from typing import Any, Mapping, Optional, Sequence

from pydantic import BaseModel, Field
from starlette.background import BackgroundTasks


class User(BaseModel):
    """用户信息"""

    class Role(BaseModel):
        """角色信息"""

        role_id: Optional[str] = Field(None, description="角色ID")
        role_code: Optional[str] = Field(None, description="角色编码")
        role_name: Optional[str] = Field(None, description="角色名称")
        permissions: Optional[Sequence[str]] = Field(None, description="权限")
        permissions_map: Optional[Mapping[str, Any]] = Field(None, description="权限映射")
        extra: Optional[Mapping[str, Any]] = Field(None, description="额外信息")

    tenant_id: str = Field(..., description="租户ID")
    user_id: str = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")
    user_type: Optional[str] = Field(None, description="用户类型")
    mobile: Optional[str] = Field(None, description="手机号")
    email: Optional[str] = Field(None, description="邮箱")
    nickname: Optional[str] = Field(None, description="昵称")
    avatar: Optional[str] = Field(None, description="头像")
    avatar_url: Optional[str] = Field(None, description="头像URL")
    roles: Optional[Sequence[Role]] = Field(None, description="角色")
    permissions: Optional[Sequence[str]] = Field(None, description="权限")
    permissions_map: Optional[Mapping[str, Any]] = Field(None, description="权限映射")
    extra: Optional[Mapping[str, Any]] = Field(None, description="额外信息")


CTX_TOKEN: ContextVar[Optional[str]] = ContextVar("token", default=None)
"""当前令牌"""
CTX_TENANT_ID: ContextVar[Optional[str]] = ContextVar("tenant_id", default=None)
"""当前租户ID"""
CTX_USER_ID: ContextVar[Optional[str]] = ContextVar("user_id", default=None)
"""当前用户ID"""
CTX_USER: ContextVar[Optional[User]] = ContextVar("user", default=None)
"""当前用户"""


CTX_BG_TASKS: ContextVar[Optional[BackgroundTasks]] = ContextVar("bg_task", default=None)
"""当前后台任务"""
