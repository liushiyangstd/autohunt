"""简历上传与版本管理（FR-1/2/3，技设 v1.2 §3.7 —— 仅 UI session）。

契约 v2 骨架：只定义 schema 与路由用于 OpenAPI 导出，业务逻辑（PDF 解析、
文件落盘 data/resumes/、引用计数）在 M3 实现。
"""

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import Response

from app.api.deps import UI_ONLY
from app.auth import require_ui
from app.schemas import ApplicationList, ErrorEnvelope, ResumeInfo, ResumeList, ResumeUpdate


class PDFResponse(Response):
    media_type = "application/pdf"

router = APIRouter(prefix="/resumes", tags=["resumes"])

UI_ERRORS = {
    401: {"model": ErrorEnvelope, "description": "UNAUTHORIZED — 未携带有效凭证"},
    403: {"model": ErrorEnvelope, "description": "FORBIDDEN — 本端点仅接受 UI session 凭证"},
}
NOT_FOUND = {404: {"model": ErrorEnvelope, "description": "NOT_FOUND"}}


@router.post(
    "",
    response_model=ResumeInfo,
    status_code=201,
    responses=UI_ERRORS,
    summary="上传简历 PDF 并创建新版本（FR-1）",
    description=(
        "multipart/form-data 上传（仅 .pdf，≤10MB；违规 422 VALIDATION_ERROR）。"
        "服务端同步解析为结构化档案（FR-2），解析结果以 parse_status/missing_fields/parse_error 表达；"
        "解析失败不阻塞（§12），返回 201 + parse_status=解析失败，用户进 D-03 手动补全。"
        "首个上传的版本自动设为默认。"
    ),
    openapi_extra={"security": UI_ONLY},
)
def create_resume(
    request: Request,
    file: UploadFile = File(description="简历 PDF 原件"),
    name: str | None = Form(default=None, description="版本名；缺省「简历 v{n}」"),
) -> ResumeInfo:
    require_ui(request)
    ...  # M3 实现：PDF 落盘 + 解析 + 档案生成


@router.get(
    "",
    response_model=ResumeList,
    responses=UI_ERRORS,
    summary="简历版本列表（D-02）",
    description="按创建时间倒序；含解析状态与引用计数（used_count）。",
    openapi_extra={"security": UI_ONLY},
)
def list_resumes(request: Request) -> ResumeList:
    require_ui(request)
    ...  # M3 实现


@router.get(
    "/{resume_id}",
    response_model=ResumeInfo,
    responses=UI_ERRORS | NOT_FOUND,
    summary="简历版本详情",
    openapi_extra={"security": UI_ONLY},
)
def get_resume(request: Request, resume_id: str) -> ResumeInfo:
    require_ui(request)
    ...  # M3 实现


@router.patch(
    "/{resume_id}",
    response_model=ResumeInfo,
    responses=UI_ERRORS | NOT_FOUND,
    summary="重命名 / 设为默认版本（FR-1）",
    description="is_default 传 true 将本版本设为默认（其余版本自动取消默认）。",
    openapi_extra={"security": UI_ONLY},
)
def update_resume(request: Request, resume_id: str, body: ResumeUpdate) -> ResumeInfo:
    require_ui(request)
    ...  # M3 实现


@router.delete(
    "/{resume_id}",
    status_code=204,
    responses=UI_ERRORS
    | NOT_FOUND
    | {
        409: {
            "model": ErrorEnvelope,
            "description": "STATE_CONFLICT — 已被投递引用，禁止删除（FR-3 回溯保护；details.used_count 给出引用数）",
        }
    },
    summary="删除简历版本",
    description="被任一投递引用的版本不可删除（D-02 置灰口径的服务端担保）。",
    openapi_extra={"security": UI_ONLY},
)
def delete_resume(request: Request, resume_id: str) -> None:
    require_ui(request)
    ...  # M3 实现


@router.get(
    "/{resume_id}/file",
    response_class=PDFResponse,
    responses=UI_ERRORS
    | NOT_FOUND
    | {200: {"content": {"application/pdf": {}}, "description": "PDF 原件（Content-Disposition: attachment）"}},
    summary="下载 PDF 原件（D-02）",
    openapi_extra={"security": UI_ONLY},
)
def get_resume_file(request: Request, resume_id: str):
    require_ui(request)
    ...  # M3 实现


@router.get(
    "/{resume_id}/references",
    response_model=ApplicationList,
    responses=UI_ERRORS | NOT_FOUND,
    summary="投递引用列表（FR-3，D-02「投递引用」Tab）",
    description="返回使用本版本简历的投递记录，可跳岗位详情（D-05）。",
    openapi_extra={"security": UI_ONLY},
)
def list_resume_references(request: Request, resume_id: str) -> ApplicationList:
    require_ui(request)
    ...  # M3 实现
