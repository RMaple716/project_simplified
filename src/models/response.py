"""
统一响应模型
确保所有接口返回统一的 JSON 格式
"""
from typing import Any, Generic, Optional, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class ResponseBase(BaseModel):
    """基础响应模型"""
    code: int = 200
    msg: str = "success"


class ResponseModel(ResponseBase, Generic[T]):
    """通用响应模型"""
    data: Optional[T] = None


class ErrorResponse(ResponseBase):
    """错误响应模型"""
    code: int = 400
    msg: str = "error"
    data: Optional[Any] = None


def success_response(data: Any = None, msg: str = "success") -> dict:
    """构建成功响应"""
    return {"code": 200, "msg": msg, "data": data}


def error_response(code: int = 400, msg: str = "error", data: Any = None) -> dict:
    """构建错误响应"""
    return {"code": code, "msg": msg, "data": data}