"""统一错误信封（§3 通用约定：{"error": {"code", "message", "details?"}}）。

422 参数校验保留 FastAPI 默认形态（契约观察项，见 docs/test/PROX-3-api-test-cases-v1.0.md §11）。
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.schemas import ErrorCode


class ApiError(Exception):
    def __init__(self, status_code: int, code: ErrorCode, message: str, details: dict | None = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def unauthorized(message: str = "未携带有效凭证") -> ApiError:
    return ApiError(401, ErrorCode.UNAUTHORIZED, message)


def forbidden(message: str = "凭证类型无权调用本端点") -> ApiError:
    return ApiError(403, ErrorCode.FORBIDDEN, message)


def not_found(message: str = "资源不存在") -> ApiError:
    return ApiError(404, ErrorCode.NOT_FOUND, message)


def permit_required(message: str = "缺少 submit_token（可提交许可）") -> ApiError:
    return ApiError(403, ErrorCode.PERMIT_REQUIRED, message)


def permit_invalid(message: str = "submit_token 无效、已过期、已消耗或与确认字段不一致") -> ApiError:
    return ApiError(403, ErrorCode.PERMIT_INVALID, message)


def state_conflict(message: str, details: dict | None = None) -> ApiError:
    return ApiError(409, ErrorCode.STATE_CONFLICT, message, details)


def validation_error(message: str, details: dict | None = None) -> ApiError:
    return ApiError(422, ErrorCode.VALIDATION_ERROR, message, details)


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    body: dict = {"error": {"code": exc.code.value, "message": exc.message}}
    if exc.details is not None:
        body["error"]["details"] = exc.details
    return JSONResponse(status_code=exc.status_code, content=body)
