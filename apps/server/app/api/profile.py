"""档案读取（FR-20，§3.2）。"""

from fastapi import APIRouter, Request
from sqlmodel import select

from autohunt_domain.models import Profile as ProfileRow
from autohunt_domain.models import Resume
from app.api.deps import ANY_CALLER
from app.auth import any_caller
from app.config import get_settings
from app.db import session_for
from app.schemas import ErrorEnvelope, Profile, ProfileEmpty

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
