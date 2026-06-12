"""用户认证路由 - 注册/登录/用户信息/密码重置（邮箱验证码模式）"""
import hashlib
import uuid
import jwt
import datetime
import re
import secrets
import smtplib
from email.message import EmailMessage
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, validator

from src.database import get_db
from src.models.db_models import User, PasswordResetToken
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


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., description="注册邮箱")

    @validator("email")
    def validate_email(cls, v):
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", v):
            raise ValueError("邮箱格式不正确")
        return v


class ResetPasswordRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6, description="邮箱收到的6位验证码")
    email: str = Field(..., description="注册邮箱")
    new_password: str = Field(..., min_length=6, max_length=100, description="新密码")

    @validator("email")
    def validate_email(cls, v):
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", v):
            raise ValueError("邮箱格式不正确")
        return v


# ==================== 邮件配置 ====================

MAIL_HOST = os.getenv("MAIL_HOST", "")
MAIL_PORT = int(os.getenv("MAIL_PORT", "465"))
MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
MAIL_FROM = os.getenv("MAIL_FROM", MAIL_USERNAME)
MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "旅途手账")
RESET_TOKEN_EXPIRE_MINUTES = int(os.getenv("RESET_TOKEN_EXPIRE_MINUTES", "30"))

FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:5173")


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


# ==================== 密码重置工具函数 ====================

def generate_reset_token() -> tuple:
    """生成密码重置令牌，返回 (原始令牌, 哈希值)"""
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    return raw_token, token_hash


def validate_reset_token(db: Session, token: str) -> User | None:
    """验证重置令牌，有效则返回对应用户，否则返回 None"""
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    record = db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == token_hash,
        PasswordResetToken.is_used == False,
        PasswordResetToken.expires_at > datetime.datetime.utcnow(),
    ).first()

    if not record:
        return None

    user = db.query(User).filter(User.user_id == record.user_id).first()
    return user


def send_reset_code_email(to_email: str, code: str) -> bool:
    """发送密码重置验证码邮件（通过 SMTP）"""
    if not MAIL_HOST or not MAIL_USERNAME:
        # 开发环境：直接打印到日志
        print(f"\n{'='*60}")
        print(f"📧 [开发模式] 密码重置验证码")
        print(f"   收件人: {to_email}")
        print(f"   验证码: {code}")
        print(f"{'='*60}\n")
        return True

    try:
        msg = EmailMessage()
        msg.set_charset('utf-8')
        msg.set_content(
            f"""您好，

您最近请求了密码重置，您的验证码为：

{code}

此验证码将在 {RESET_TOKEN_EXPIRE_MINUTES} 分钟后过期。
如非本人操作，请忽略此邮件。

- {MAIL_FROM_NAME} 团队
"""
        )
        msg.add_alternative(
            f"""<html>
<body style="font-family: 'Segoe UI', Arial, sans-serif; padding: 20px; color: #333;">
    <div style="max-width: 560px; margin: 0 auto; border: 1px solid #e0d8ce; padding: 32px; background: #faf7f2;">
        <h2 style="text-align: center; font-family: Georgia, serif; color: #5a4a3a;">旅途手账</h2>
        <p style="font-size: 15px; line-height: 1.6;">您好，</p>
        <p style="font-size: 15px; line-height: 1.6;">
            您最近请求了密码重置，请在页面中输入以下验证码：
        </p>
        <div style="text-align: center; margin: 28px 0; padding: 20px; background: #f0ebe5; border-radius: 8px;">
            <span style="font-size: 36px; font-weight: bold; letter-spacing: 12px; color: #5a4a3a; font-family: monospace;">
                {code}
            </span>
        </div>
        <p style="font-size: 13px; color: #8a7a70;">
            此验证码将在 {RESET_TOKEN_EXPIRE_MINUTES} 分钟后过期。
        </p>
        <p style="font-size: 13px; color: #8a7a70;">
            如非本人操作，请忽略此邮件。
        </p>
        <hr style="border: none; border-top: 1px solid #e0d8ce; margin: 24px 0;">
        <p style="font-size: 12px; color: #b0a090; text-align: center;">- {MAIL_FROM_NAME} 团队</p>
    </div>
</body>
</html>""",
            subtype="html",
        )
        msg["Subject"] = f"【{MAIL_FROM_NAME}】密码重置验证码"
        msg["From"] = f"{MAIL_FROM_NAME} <{MAIL_FROM}>"
        msg["To"] = to_email

        smtp_user = MAIL_FROM if '@' in MAIL_FROM else MAIL_USERNAME

        if MAIL_PORT == 465:
            with smtplib.SMTP_SSL(MAIL_HOST, MAIL_PORT) as server:
                server.login(smtp_user, MAIL_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(MAIL_HOST, MAIL_PORT) as server:
                server.starttls()
                server.login(smtp_user, MAIL_PASSWORD)
                server.send_message(msg)

        print(f"✅ 密码重置验证码邮件已发送至 {to_email}")
        return True

    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")
        return False


def mark_old_tokens_used(db: Session, user_id: str):
    """将用户所有未使用的过期令牌标记为已使用"""
    now = datetime.datetime.utcnow()
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user_id,
        PasswordResetToken.is_used == False,
        PasswordResetToken.expires_at <= now,
    ).update({"is_used": True})
    db.commit()


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
# ==================== 密码重置路由 ====================


@router.post("/forgot-password", response_model=dict)
async def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """请求密码重置（发送6位验证码邮件）"""
    # 不论用户是否存在都返回相同提示，防止邮箱枚举
    user = db.query(User).filter(User.email == request.email).first()

    if user:
        # 清理该用户旧的过期令牌
        mark_old_tokens_used(db, str(user.user_id))

        # 生成6位随机数字验证码
        code = f"{random.randint(0, 999999):06d}"
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)

        # 存入数据库
        reset_record = PasswordResetToken(
            user_id=user.user_id,
            token_hash=code_hash,
            expires_at=expires_at,
        )
        db.add(reset_record)
        db.commit()

        # 发送验证码邮件
        send_reset_code_email(str(user.email), code)

    return {
        "code": 200,
        "msg": "验证码已发送（如该邮箱已注册，请查收邮件）",
        "data": None,
    }


@router.post("/reset-password", response_model=dict)
async def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    """使用验证码重置密码"""
    # 查找用户
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(status_code=400, detail="邮箱未注册")

    # 验证验证码
    code_hash = hashlib.sha256(request.code.encode()).hexdigest()
    record = db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.user_id,
        PasswordResetToken.token_hash == code_hash,
        PasswordResetToken.is_used == False,
        PasswordResetToken.expires_at > datetime.datetime.utcnow(),
    ).first()

    if not record:
        raise HTTPException(status_code=400, detail="验证码无效或已过期")

    # 更新密码
    setattr(user, "password_hash", hash_password(request.new_password))

    # 标记令牌已使用
    setattr(record, "is_used", True)

    # 使该用户所有其他未使用令牌也失效
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.user_id,
        PasswordResetToken.is_used == False,
    ).update({"is_used": True})

    db.commit()

    return {
        "code": 200,
        "msg": "密码重置成功，请使用新密码登录",
        "data": None,
    }