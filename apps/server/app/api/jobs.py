"""岗位读写（FR-21，§3.3）。"""

from fastapi import APIRouter, status

from app.api.deps import ANY_CALLER
from app.schemas import ErrorEnvelope, Job, JobCreate, JobDuplicate, JobList, JobUpdate

router = APIRouter(prefix="/jobs", tags=["jobs"])

COMMON_ERRORS = {
    401: {"model": ErrorEnvelope, "description": "UNAUTHORIZED — 未携带有效凭证"},
}


@router.post(
    "",
    response_model=Job,
    status_code=status.HTTP_201_CREATED,
    responses={
        **COMMON_ERRORS,
        200: {
            "model": JobDuplicate,
            "description": "BR-3：同公司同岗位重复创建 → 200 + duplicate_of，提示不拦截",
        },
    },
    summary="创建岗位",
    openapi_extra={"security": ANY_CALLER},
)
def create_job(body: JobCreate) -> Job: ...


@router.get(
    "",
    response_model=JobList,
    responses=COMMON_ERRORS,
    summary="岗位列表",
    description="分页：?cursor=&limit=（默认 50）。",
    openapi_extra={"security": ANY_CALLER},
)
def list_jobs(cursor: str | None = None, limit: int = 50) -> JobList: ...


@router.get(
    "/{job_id}",
    response_model=Job,
    responses={
        **COMMON_ERRORS,
        404: {"model": ErrorEnvelope, "description": "NOT_FOUND"},
    },
    summary="岗位详情",
    openapi_extra={"security": ANY_CALLER},
)
def get_job(job_id: str) -> Job: ...


@router.patch(
    "/{job_id}",
    response_model=Job,
    responses={
        **COMMON_ERRORS,
        404: {"model": ErrorEnvelope, "description": "NOT_FOUND"},
    },
    summary="更新岗位字段（公司/岗位名/JD 链接/地点/渠道/截止日期）",
    openapi_extra={"security": ANY_CALLER},
)
def update_job(job_id: str, body: JobUpdate) -> Job: ...
