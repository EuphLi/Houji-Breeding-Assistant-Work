"""SMS 验证码服务 —— 发送、验证、登录/注册编排。"""

from __future__ import annotations

import hashlib
import os
import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.services.run_queue_service import get_redis_client
from yuxi.services.sms_provider import (
    DypnsapiProvider,
    LogSmsProvider,
    RateLimitError,
    SmsSendError,
    SmsProvider,
)
from yuxi.storage.postgres.models_business import Department, User
from yuxi.utils import logger
from yuxi.utils.datetime_utils import utc_now_naive

IP_LIMIT_KEY = "sms:ip:{}"
COOLDOWN_TTL = int(os.getenv("SMS_COOLDOWN_TTL", "60"))

_provider: SmsProvider | None = None


def _get_mode() -> str:
    return os.getenv("SMS_MODE", "").strip().lower() or os.getenv("SMS_PROVIDER", "log").strip().lower()


def _get_provider() -> SmsProvider:
    global _provider
    if _provider is None:
        mode = _get_mode()
        if mode == "log":
            _provider = LogSmsProvider()
        elif mode == "dypnsapi":
            _provider = DypnsapiProvider()
        else:
            raise ValueError(f"未知的 SMS_MODE: {mode}")
    return _provider


def is_dev_provider() -> bool:
    return _get_mode() == "log"


def ip_key(client_ip: str) -> str:
    return IP_LIMIT_KEY.format(hashlib.sha256(client_ip.encode()).hexdigest()[:16])


async def send_verification_code(phone: str, client_ip: str) -> None:
    """发送验证码，含 IP 限流。手机号冷却和验证码存储由 Provider 负责。"""
    redis = await get_redis_client()

    ip_k = ip_key(client_ip)
    if await redis.exists(ip_k):
        raise RateLimitError("请求过于频繁，请 60 秒后再试")
    await redis.setex(ip_k, COOLDOWN_TTL, "1")

    provider = _get_provider()
    result = await provider.send(phone)

    if not result.success:
        raise SmsSendError(result.message)


async def verify_code(phone: str, code: str) -> bool:
    """验证验证码，委托给 Provider。"""
    provider = _get_provider()
    result = await provider.verify(phone, code)
    return result.success


async def get_latest_code(phone: str) -> str | None:
    """仅开发环境使用：获取最新验证码。"""
    provider = _get_provider()
    if isinstance(provider, LogSmsProvider):
        return await provider.get_latest_code(phone)
    return None


async def login_or_register_by_phone(phone: str, db: AsyncSession) -> dict:
    """通过手机号查找或自动注册用户，返回 Token 所需字段。"""
    result = await db.execute(select(User).filter(User.phone_number == phone))
    user = result.scalar_one_or_none()

    if user is None:
        user = await _create_user_by_phone(phone, db)
    elif user.is_deleted:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="该账户已注销")

    user.last_login = utc_now_naive()
    await db.commit()

    department_name = None
    if user.department_id:
        result = await db.execute(select(Department.name).filter(Department.id == user.department_id))
        department_name = result.scalar_one_or_none()

    return {
        "user_id": user.id,
        "username": user.username,
        "user_id_login": user.user_id,
        "phone_number": user.phone_number,
        "avatar": user.avatar,
        "role": user.role,
        "department_id": user.department_id,
        "department_name": department_name,
    }


async def _create_user_by_phone(phone: str, db: AsyncSession) -> User:
    """用手机号自动注册新用户。"""
    from server.utils.auth_utils import AuthUtils
    from server.utils.user_utils import generate_unique_user_id

    result = await db.execute(select(Department).filter(Department.name == "默认部门"))
    dept = result.scalar_one_or_none()

    existing_result = await db.execute(select(User.user_id))
    existing_ids = [row[0] for row in existing_result.fetchall()]

    username = phone
    user_id_str = generate_unique_user_id(username, existing_ids)

    random_password = secrets.token_hex(32)
    password_hash = AuthUtils.hash_password(random_password)

    user = User(
        username=username,
        user_id=user_id_str,
        phone_number=phone,
        password_hash=password_hash,
        role="user",
        department_id=dept.id if dept else None,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info(f"Auto-registered user via SMS: {phone} (id={user.id}, user_id={user_id_str})")
    return user
