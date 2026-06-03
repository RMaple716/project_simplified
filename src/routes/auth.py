"""用户认证路由 - 注册/登录/用户信息"""
import hashlib
import uuid
import jwt
import datetime
import re
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, validator

from src.database import get_db
from src.models.db_models import User
import os
import random

# JWT 配置
JWT_SECRET = os.getenv("JWT_SECRET", "travel-planner-jwt-secret-key-2026-secure")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
# Token 有效期：默认 7 天（168小时）。可通过环境变量 JWT_EXPIRE_HOURS 覆盖
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "7"))

router = APIRouter(prefix="/api/v1/auth", tags=["用户认证"])


# ==================== 请求/响应模型 ====================

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50, description="用户名")
    email: str = Field(..., description="邮箱")
    password: str = Field(..., min_length=6, max_length=100, description="密码")

    @validator("email")
    def validate_email(cls, v):
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", v):
            raise ValueError("邮箱格式不正确")
        return v

    @validator("username")
    def validate_username(cls, v):
        if not re.match(r"^[a-zA-Z0-9_\u4e00-\u9fa5]{2,50}$", v):
            raise ValueError("用户名只能包含中文、字母、数字和下划线")
        return v


class LoginRequest(BaseModel):
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


# ==================== 工具函数 ====================

def hash_password(password: str) -> str:
    """使用 SHA-256 哈希密码"""
    return hashlib.sha256(password.encode()).hexdigest()


def create_token(user_id: str, username: str) -> str:
    """生成 JWT token"""
    payload = {
        "user_id": user_id,
        "username": username,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=JWT_EXPIRE_HOURS),
        "iat": datetime.datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict | None:
    """验证 JWT token，返回 payload 或 None"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ==================== 获取当前用户依赖 ====================

async def get_current_user(
    authorization: str = Header(None, description="Bearer token"),
    db: Session = Depends(get_db),
) -> User:
    """从请求头中解析 token 并获取当前用户"""
    if not authorization:
        raise HTTPException(status_code=401, detail="未提供认证令牌")
    
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="认证令牌格式错误")
    
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="认证令牌无效或已过期")
    
    user = db.query(User).filter(User.user_id == payload["user_id"]).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    if not bool(user.is_active):
        raise HTTPException(status_code=401, detail="账号已被禁用")
    
    return user


# ==================== 路由 ====================

@router.post("/register", response_model=dict)
async def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """用户注册"""
    # 检查用户名是否已存在
    existing = db.query(User).filter(User.username == request.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已被注册")
    
    # 检查邮箱是否已存在
    existing_email = db.query(User).filter(User.email == request.email).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="邮箱已被注册")
    short_id = f"u{datetime.datetime.now().strftime('%H%M%S')}{random.randint(1000, 9999)}"
    # 创建用户
    user = User(
        user_id=short_id,
        username=request.username,
        email=request.email,
        password_hash=hash_password(request.password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    
    user_id = str(user.user_id)  # 或用 getattr
    username = str(user.username)
    # 生成 token
    token = create_token(user_id, username)
    
    return {
        "code": 200,
        "msg": "注册成功",
        "data": {
            "access_token": token,
            "token_type": "bearer",
            "user_id": user.user_id,
            "username": user.username,
            "email": user.email
        }
    }


@router.post("/login", response_model=dict)
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    """用户登录"""
    # 查找用户（支持用户名或邮箱登录）
    user = db.query(User).filter(
        (User.username == request.username) | (User.email == request.username)
    ).first()
    
    if not user:
        raise HTTPException(status_code=400, detail="用户名或密码错误")
    
    if hash_password(request.password) != user.password_hash:
        raise HTTPException(status_code=400, detail="用户名或密码错误")
    
    if not bool(user.is_active):
        raise HTTPException(status_code=400, detail="账号已被禁用")
    
    user_id = str(user.user_id)  # 或用 getattr
    username = str(user.username)
    # 生成 token
    token = create_token(user_id, username)
    
    return {
        "code": 200,
        "msg": "登录成功",
        "data": {
            "access_token": token,
            "token_type": "bearer",
            "user_id": user.user_id,
            "username": user.username,
            "email": user.email
        }
    }


@router.get("/me", response_model=dict)
async def get_me(current_user: User = Depends(get_current_user)):
    """获取当前用户信息"""
    return {
        "code": 200,
        "msg": "success",
        "data": {
            "user_id": current_user.user_id,
            "username": current_user.username,
            "email": current_user.email,
            "avatar": current_user.avatar,
            "created_at": current_user.created_at.strftime("%Y-%m-%d %H:%M:%S") if current_user.created_at is not None else "",
        }
    }