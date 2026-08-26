"""档案读取（FR-20，§3.2）与档案写（FR-2/3，技设 v1.2 §3.7）。

显式保存语义（D-03）：全量替换，不做自动保存——档案是 Agent 填表的数据源，
半完成状态不应被 Agent 读到。保存后重算简历的缺失必填标记（AC-1）。
"""

from fastapi import APIRouter, Request
from sqlmodel import select

from autohunt_domain.models import EmailAccount
from autohunt_domain.models import Profile as ProfileRow
from autohunt_domain.models import Resume
from app.api.deps import ANY_CALLER, UI_ONLY
from app.auth import any_caller, require_ui
from app.config import get_settings
from app.db import session_for
from app.errors import not_found
from app.schemas import ErrorEnvelope, Profile, ProfileEmpty, ProfileUpdate
from app.services.resume_parse import missing_required

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get(
    "",
    response_model=Profile | ProfileEmpty,
    responses={
        401: {"model": ErrorEnvelope, "description": "UNAUTHORIZED — 未携带有效凭证"},
    },
    summary="读取结构化档案",
    description=(
        "返回指定简历版本的结构化档案（字段与 §10.1 字典一一对应）；缺省 resume_id 返回默认简历版本。"
        "无简历时返回 200 + {\"empty\": true}（§12 空态，Agent 可据此提示「先完善档案」）。"
    ),
    openapi_extra={"security": ANY_CALLER},
)
def get_profile(request: Request, resume_id: str | None = None) -> Profile | ProfileEmpty:
    any_caller(request)
    with session_for(get_settings().data_dir) as session:
        if resume_id is None:
            resume = session.exec(select(Resume).where(Resume.is_default.is_(True))).first()
            if resume is None:
                return ProfileEmpty()
            resume_id = resume.id
        row = session.exec(
            select(ProfileRow)
            .where(ProfileRow.resume_id == resume_id)
            .order_by(ProfileRow.resume_version.desc())
        ).first()
        if row is None:
            return ProfileEmpty()
        return Profile(
            name=row.name,
            phone=row.phone,
            email=row.email,
            educations=row.educations,
            experiences=row.experiences,
            skills=row.skills,
            awards=row.awards,
            expected_city=row.expected_city,
            expected_position=row.expected_position,
            resume_id=row.resume_id,
            resume_version=row.resume_version,
        )


@router.put(
    "",
    response_model=Profile,
    responses={
        401: {"model": ErrorEnvelope, "description": "UNAUTHORIZED — 未携带有效凭证"},
        403: {"model": ErrorEnvelope, "description": "FORBIDDEN — 本端点仅接受 UI session 凭证"},
        404: {"model": ErrorEnvelope, "description": "NOT_FOUND — resume_id 不存在"},
    },
    summary="保存结构化档案（FR-2/3，D-03 显式保存）",
    description=(
        "全量替换指定简历版本的档案字段（§10.1 字典）。显式保存语义：不用自动保存——"
        "档案是 Agent 填表的数据源，半完成状态不应被 Agent 读到（D-03）。"
        "email 传 null/省略时按 §3.2 默认回填已绑定求职邮箱。"
        "契约 v2 骨架：本端点业务逻辑在 M3 实现。"
    ),
    openapi_extra={"security": UI_ONLY},
)
def put_profile(request: Request, body: ProfileUpdate) -> Profile:
    require_ui(request)
    with session_for(get_settings().data_dir) as session:
        resume = session.exec(select(Resume).where(Resume.id == body.resume_id)).first()
        if resume is None:
            raise not_found("简历版本不存在")

        email = body.email
        if email is None:
            # §3.2 注：email 省略时默认回填已绑定求职邮箱（优先 active 账户）
            account = session.exec(
                select(EmailAccount).order_by(EmailAccount.status != "active", EmailAccount.seq)
            ).first()
            if account is not None:
                email = account.email

        row = session.exec(
            select(ProfileRow)
            .where(ProfileRow.resume_id == body.resume_id)
            .order_by(ProfileRow.resume_version.desc())
        ).first()
        if row is None:
            row = ProfileRow(resume_id=body.resume_id, resume_version=resume.version)
        row.name = body.name
        row.phone = body.phone
        row.email = email
        row.educations = [e.model_dump() for e in body.educations]
        row.experiences = [e.model_dump() for e in body.experiences]
        row.skills = body.skills
        row.awards = body.awards
        row.expected_city = body.expected_city
        row.expected_position = body.expected_position
        session.add(row)

        # AC-1：显式保存后重算缺失必填标记，消除/刷新 D-02 解析状态
        missing = missing_required({"name": row.name, "phone": row.phone, "email": row.email})
        resume.missing_fields = missing
        resume.parse_status = "解析完成" if not missing else "部分字段缺失"
        if resume.parse_status != "解析失败":
            resume.parse_error = None
        session.add(resume)

        session.commit()
        session.refresh(row)
        return Profile(
            name=row.name,
            phone=row.phone,
            email=row.email,
            educations=row.educations,
            experiences=row.experiences,
            skills=row.skills,
            awards=row.awards,
            expected_city=row.expected_city,
            expected_position=row.expected_position,
            resume_id=row.resume_id,
            resume_version=row.resume_version,
        )
