"""开发环境调试端点（仅在 SMS_MODE=log 时注册）。"""

from fastapi import APIRouter, HTTPException, Query, status

from yuxi.services.sms_service import get_latest_code

dev = APIRouter(prefix="/dev", tags=["development"])


@dev.get("/verification-code")
async def get_verification_code(phone: str = Query(..., description="手机号")):
    """获取最新验证码（仅开发环境可用）"""
    code = await get_latest_code(phone)
    if code is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该手机号没有有效的验证码",
        )
    return {"phone": phone, "code": code}
