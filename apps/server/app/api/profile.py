"""档案读取（FR-20，§3.2）。"""

from fastapi import APIRouter

from app.api.deps import ANY_CALLER
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
def get_profile(resume_id: str | None = None) -> Profile | ProfileEmpty: ...
