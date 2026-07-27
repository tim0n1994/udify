"""API 请求/响应模型（API-01，2026-08 批次 4B）。

统一响应信封 ``{success, data, error, meta}``（ADR-v3-007）；错误体是
ErrorRecord（code 遵循 DOMAIN_CATEGORY_DETAIL），前端据 ``retryable`` 与
``suggested_action`` 决定交互，不解析 message 文本。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateJobRequest(BaseModel):
    game_root: str = Field(min_length=1, description="miu2d 游戏根目录绝对路径")
    intent: str = Field(min_length=1, description="自然语言修改意图")


class RejectRequest(BaseModel):
    reason: str = ""


class ErrorModel(BaseModel):
    code: str
    message: str
    owner_module: str
    retryable: bool = False
    suggested_action: str = ""


class Envelope(BaseModel):
    """所有 JSON 端点的统一信封（包下载除外）。"""

    success: bool
    data: Any = None
    error: ErrorModel | None = None
    meta: dict[str, Any] | None = None


__all__ = ["CreateJobRequest", "Envelope", "ErrorModel", "RejectRequest"]
