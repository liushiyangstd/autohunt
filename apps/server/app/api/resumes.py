"""简历上传与版本管理（FR-1/2/3，技设 v1.2 §3.7 —— 仅 UI session）。

PDF 原件落盘 data/resumes/；上传即同步解析（services.resume_parse），
解析失败不阻塞（§12）：返回 201 + parse_status=解析失败，用户进 D-03 手动补全。
"""

from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import Response
from sqlmodel import select

from autohunt_domain.models import Application as ApplicationRow
from autohunt_domain.models import Profile as ProfileRow
from autohunt_domain.models import Resume
from app.api.deps import UI_ONLY
from app.auth import require_ui
from app.config import get_settings
from app.db import session_for
from app.errors import not_found, state_conflict, validation_error
from app.schemas import (
    Application,
    ApplicationList,
    ApplicationStatus,
    ErrorEnvelope,
    ResumeInfo,
    ResumeList,
    ResumeParseStatus,
    ResumeUpdate,
)
from app.services import resume_parse

MAX_PDF_BYTES = 10 * 1024 * 1024


class PDFResponse(Response):
    media_type = "application/pdf"

router = APIRouter(prefix="/resumes", tags=["resumes"])

UI_ERRORS = {
    401: {"model": ErrorEnvelope, "description": "UNAUTHORIZED — 未携带有效凭证"},
    403: {"model": ErrorEnvelope, "description": "FORBIDDEN — 本端点仅接受 UI session 凭证"},
}
NOT_FOUND = {404: {"model": ErrorEnvelope, "description": "NOT_FOUND"}}


def _used_count(session, resume_id: str) -> int:
    return len(
        session.exec(select(ApplicationRow).where(ApplicationRow.resume_id == resume_id)).all()
    )


def _to_info(session, row: Resume) -> ResumeInfo:
    profile = session.exec(
        select(ProfileRow)
        .where(ProfileRow.resume_id == row.id)
        .order_by(ProfileRow.resume_version.desc())
    ).first()
    return ResumeInfo(
        id=row.id,
        name=row.name,
        version=profile.resume_version if profile else row.version,
        is_default=row.is_default,
        parse_status=ResumeParseStatus(row.parse_status),
        missing_fields=row.missing_fields,
        parse_error=row.parse_error,
        used_count=_used_count(session, row.id),
        created_at=row.created_at,
    )


def _get_or_404(session, resume_id: str) -> Resume:
    row = session.exec(select(Resume).where(Resume.id == resume_id)).first()
    if row is None:
        raise not_found("简历版本不存在")
    return row


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
async def create_resume(
    request: Request,
    file: UploadFile = File(description="简历 PDF 原件"),
    name: str | None = Form(default=None, description="版本名；缺省「简历 v{n}」"),
) -> ResumeInfo:
    require_ui(request)
    if not (file.filename or "").lower().endswith(".pdf"):
        raise validation_error("仅支持 .pdf 格式简历")
    content = await file.read()
    if len(content) > MAX_PDF_BYTES:
        raise validation_error("简历 PDF 超过 10MB 上限")
    if not content:
        raise validation_error("上传文件为空")
    if not content.startswith(b"%PDF"):
        # AC-9：校验内容签名，改扩展名的非 PDF 文件返回 422 且不落库
        raise validation_error("文件内容不是合法 PDF")

    settings = get_settings()
    with session_for(settings.data_dir) as session:
        version = len(session.exec(select(Resume)).all()) + 1
        row = Resume(name=name or f"简历 v{version}", version=version, file_path="")
        row.file_path = f"resumes/{row.id}.pdf"
        row.is_default = version == 1  # 首个上传版本自动设为默认

        parse_status, fields, missing, parse_error = resume_parse.parse_resume(content, settings)
        row.parse_status = parse_status
        row.missing_fields = missing
        row.parse_error = parse_error
        session.add(row)
        session.flush()  # FK 到 resume.id（非 PK 唯一列），SQLAlchemy 不自动排序，先落 resume 再建 profile

        profile = ProfileRow(
            resume_id=row.id,
            resume_version=version,
            name=fields.get("name"),
            phone=fields.get("phone"),
            email=fields.get("email"),
            educations=fields.get("educations", []),
            experiences=fields.get("experiences", []),
            skills=fields.get("skills", []),
            awards=fields.get("awards", []),
            expected_city=fields.get("expected_city"),
            expected_position=fields.get("expected_position"),
        )
        session.add(profile)

        target = Path(settings.data_dir) / row.file_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

        session.commit()
        session.refresh(row)
        return _to_info(session, row)


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
    with session_for(get_settings().data_dir) as session:
        rows = session.exec(select(Resume).order_by(Resume.seq.desc())).all()
        return ResumeList(items=[_to_info(session, row) for row in rows])


@router.get(
    "/{resume_id}",
    response_model=ResumeInfo,
    responses=UI_ERRORS | NOT_FOUND,
    summary="简历版本详情",
    openapi_extra={"security": UI_ONLY},
)
def get_resume(request: Request, resume_id: str) -> ResumeInfo:
    require_ui(request)
    with session_for(get_settings().data_dir) as session:
        return _to_info(session, _get_or_404(session, resume_id))


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
    with session_for(get_settings().data_dir) as session:
        row = _get_or_404(session, resume_id)
        if body.name is not None:
            row.name = body.name
        if body.is_default:
            for other in session.exec(select(Resume).where(Resume.id != resume_id)).all():
                other.is_default = False
                session.add(other)
            row.is_default = True
        session.add(row)
        session.commit()
        session.refresh(row)
        return _to_info(session, row)


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
    settings = get_settings()
    with session_for(settings.data_dir) as session:
        row = _get_or_404(session, resume_id)
        used = _used_count(session, resume_id)
        if used > 0:
            raise state_conflict("该简历版本已被投递引用，禁止删除（FR-3 回溯保护）", details={"used_count": used})
        for profile in session.exec(select(ProfileRow).where(ProfileRow.resume_id == resume_id)).all():
            session.delete(profile)
        session.delete(row)
        file_path = Path(settings.data_dir) / row.file_path
        session.commit()
        file_path.unlink(missing_ok=True)


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
    settings = get_settings()
    with session_for(settings.data_dir) as session:
        row = _get_or_404(session, resume_id)
        file_path = Path(settings.data_dir) / row.file_path
    if not file_path.exists():
        raise not_found("简历 PDF 文件缺失")
    ascii_name = (row.name or "resume").encode("ascii", errors="ignore").decode() or "resume"
    return PDFResponse(
        content=file_path.read_bytes(),
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_name}.pdf"; '
                f"filename*=UTF-8''{quote(row.name or 'resume')}.pdf"
            )
        },
    )


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
    with session_for(get_settings().data_dir) as session:
        _get_or_404(session, resume_id)
        rows = session.exec(
            select(ApplicationRow).where(ApplicationRow.resume_id == resume_id).order_by(ApplicationRow.seq)
        ).all()
        return ApplicationList(
            items=[
                Application(
                    id=row.id,
                    job_id=row.job_id,
                    resume_id=row.resume_id,
                    applied_at=row.applied_at,
                    status=ApplicationStatus(row.status),
                    interview_round=row.interview_round,
                    note=row.note,
                )
                for row in rows
            ],
            next_cursor=None,
        )
