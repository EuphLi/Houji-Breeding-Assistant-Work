"""SMS Provider 策略层 —— 支持 Log (开发/自生成) 和 Dypnsapi (阿里云号码认证) 两种模式。"""

from __future__ import annotations

import hashlib
import os
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from yuxi.utils import logger


@dataclass
class SendResult:
    success: bool
    message: str = ""
    extra: dict | None = None


@dataclass
class VerifyResult:
    success: bool
    message: str = ""
    extra: dict | None = None


class RateLimitError(Exception):
    pass


class SmsSendError(Exception):
    pass


class SmsProvider(ABC):
    """SMS 发送 + 验证策略抽象基类"""

    @abstractmethod
    async def send(self, phone: str) -> SendResult:
        """发送验证码"""
        ...

    @abstractmethod
    async def verify(self, phone: str, code: str) -> VerifyResult:
        """验证验证码"""
        ...


# --- LogSmsProvider (自生成模式) ---

CODE_KEY = "sms:code:{}"
ATTEMPTS_KEY = "sms:attempts:{}"
COOLDOWN_KEY = "sms:cooldown:{}"

CODE_TTL = int(os.getenv("SMS_CODE_TTL", "300"))
COOLDOWN_TTL = int(os.getenv("SMS_COOLDOWN_TTL", "60"))
MAX_ATTEMPTS = int(os.getenv("SMS_MAX_ATTEMPTS", "3"))


class LogSmsProvider(SmsProvider):
    """开发/测试用：自生成验证码，Redis 存储，不实际发送 SMS"""

    @staticmethod
    def _generate_code() -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    async def send(self, phone: str) -> SendResult:
        from yuxi.services.run_queue_service import get_redis_client

        redis = await get_redis_client()

        cooldown_k = COOLDOWN_KEY.format(phone)
        if await redis.exists(cooldown_k):
            raise RateLimitError("验证码已发送，请 60 秒后再试")

        code = self._generate_code()

        await redis.setex(CODE_KEY.format(phone), CODE_TTL, code)
        await redis.setex(ATTEMPTS_KEY.format(phone), CODE_TTL, "0")
        await redis.setex(cooldown_k, COOLDOWN_TTL, "1")

        from yuxi.utils import logger

        logger.info(f"SMS code for {phone}: {code}")

        return SendResult(success=True, message="验证码已发送", extra={"code": code})

    async def verify(self, phone: str, code: str) -> VerifyResult:
        from yuxi.services.run_queue_service import get_redis_client

        redis = await get_redis_client()

        stored = await redis.get(CODE_KEY.format(phone))
        if stored is None:
            return VerifyResult(success=False, message="验证码已过期")

        if stored == code:
            await redis.delete(CODE_KEY.format(phone))
            await redis.delete(ATTEMPTS_KEY.format(phone))
            return VerifyResult(success=True, message="验证通过")

        attempts = await redis.incr(ATTEMPTS_KEY.format(phone))
        if attempts >= MAX_ATTEMPTS:
            await redis.delete(CODE_KEY.format(phone))
            await redis.delete(ATTEMPTS_KEY.format(phone))
            return VerifyResult(success=False, message="验证码错误次数过多，已失效")

        return VerifyResult(success=False, message="验证码错误")

    async def get_latest_code(self, phone: str) -> str | None:
        from yuxi.services.run_queue_service import get_redis_client

        redis = await get_redis_client()
        return await redis.get(CODE_KEY.format(phone))


# --- DypnsapiProvider (阿里云号码认证托管模式) ---


class DypnsapiProvider(SmsProvider):
    """阿里云号码认证服务 —— 阿里云生成验证码、发送、核验"""

    def __init__(self):
        self._access_key_id = os.getenv("ALIYUN_ACCESS_KEY_ID", "").strip()
        self._access_key_secret = os.getenv("ALIYUN_ACCESS_KEY_SECRET", "").strip()
        self._sign_name = os.getenv("DYPNSAPI_SIGN_NAME", "").strip()
        self._template_code = os.getenv("DYPNSAPI_TEMPLATE_CODE", "").strip()
        self._template_param = os.getenv("DYPNSAPI_TEMPLATE_PARAM", '{"code":"##code##"}').strip()
        self._code_length = int(os.getenv("DYPNSAPI_CODE_LENGTH", "6"))
        self._code_type = int(os.getenv("DYPNSAPI_CODE_TYPE", "1"))
        self._scheme_name = os.getenv("DYPNSAPI_SCHEME_NAME", "").strip() or None

    def _get_client(self):
        try:
            from alibabacloud_dypnsapi20170525.client import Client as DypnsapiClient
            from alibabacloud_tea_openapi import models as open_api_models
        except ImportError as e:
            raise ImportError(
                "DypnsapiProvider 需要安装阿里云 SDK: pip install alibabacloud_dypnsapi20170525"
            ) from e

        config = open_api_models.Config(
            access_key_id=self._access_key_id,
            access_key_secret=self._access_key_secret,
            region_id="cn-hangzhou",
        )
        config.endpoint = "dypnsapi.aliyuncs.com"
        return DypnsapiClient(config)

    async def send(self, phone: str) -> SendResult:
        import asyncio

        try:
            from alibabacloud_dypnsapi20170525 import models as dypnsapi_models
            from alibabacloud_tea_util import models as util_models
        except ImportError as e:
            raise ImportError(
                "DypnsapiProvider 需要安装阿里云 SDK: pip install alibabacloud_dypnsapi20170525"
            ) from e

        client = self._get_client()

        request = dypnsapi_models.SendSmsVerifyCodeRequest(
            phone_number=phone,
            sign_name=self._sign_name,
            template_code=self._template_code,
            template_param=self._template_param,
            code_length=self._code_length,
            code_type=self._code_type,
            scheme_name=self._scheme_name,
        )

        def _call():
            runtime = util_models.RuntimeOptions()
            return client.send_sms_verify_code_with_options(request, runtime)

        try:
            response = await asyncio.to_thread(_call)
            body = response.body.to_map()
            logger.info(f"Dypnsapi send response: {body}")
            ok = body.get("Code") == "OK"
            return SendResult(
                success=ok,
                message=body.get("Message", ""),
                extra=body,
            )
        except Exception as e:
            logger.error(f"Dypnsapi send error: {e}")
            return SendResult(success=False, message=str(e))

    async def verify(self, phone: str, code: str) -> VerifyResult:
        import asyncio

        try:
            from alibabacloud_dypnsapi20170525 import models as dypnsapi_models
            from alibabacloud_tea_util import models as util_models
        except ImportError as e:
            raise ImportError(
                "DypnsapiProvider 需要安装阿里云 SDK: pip install alibabacloud_dypnsapi20170525"
            ) from e

        client = self._get_client()

        request = dypnsapi_models.CheckSmsVerifyCodeRequest(
            phone_number=phone,
            verify_code=code,
            scheme_name=self._scheme_name,
        )

        def _call():
            runtime = util_models.RuntimeOptions()
            return client.check_sms_verify_code_with_options(request, runtime)

        try:
            response = await asyncio.to_thread(_call)
            body = response.body.to_map()
            logger.info(f"Dypnsapi verify response: {body}")
            # CheckSmsVerifyCode: Code=OK 且 Model.VerifyResult=true 才算核验通过
            model = body.get("Model") or {}
            ok = body.get("Code") == "OK" and model.get("VerifyResult", True) is not False
            return VerifyResult(
                success=ok,
                message=body.get("Message", ""),
                extra=body,
            )
        except Exception as e:
            logger.error(f"Dypnsapi verify error: {e}")
            return VerifyResult(success=False, message=str(e))
