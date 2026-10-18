from fastapi import Depends, FastAPI, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.car_client import CarServiceClient
from app.config import Settings
from app.report import build_report
from app.tokens import InvalidToken, TokenVerifier, load_public_key

JOBS_CREATE = "jobs:create"
JOB_SCOPES = frozenset({"cars:read", "valuations:read", "reports:create"})
SELLER = "seller"


class JobIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    car_id: int = Field(ge=1)
    job_token: str = Field(min_length=1, max_length=4096)


class JobOut(BaseModel):
    job_id: str
    car_id: int
    report_id: int


def _unauthorized():
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden():
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def service_principal(request: Request):
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token or " " in token:
        raise _unauthorized()
    try:
        principal = request.app.state.verifier.verify_service_token(token)
    except InvalidToken:
        raise _unauthorized()
    if JOBS_CREATE not in principal.scopes or principal.role != SELLER:
        raise _forbidden()
    return principal


def create_app(settings=None, transport=None):
    settings = settings or Settings.from_env()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.verifier = TokenVerifier(load_public_key(settings.public_key_file))
    app.state.car_service = CarServiceClient(settings.car_service_url, transport=transport)

    @app.post("/jobs", response_model=JobOut, status_code=status.HTTP_201_CREATED)
    def create_job(body: JobIn, principal=Depends(service_principal)):
        try:
            grant = app.state.verifier.verify_job_token(body.job_token)
        except InvalidToken:
            raise _forbidden()
        if grant.subject != principal.subject or grant.car_id != body.car_id:
            raise _forbidden()
        if not JOB_SCOPES <= grant.scopes:
            raise _forbidden()

        report = app.state.car_service.run_job(body.job_token, grant.car_id, build_report)
        return JobOut(job_id=grant.job_id, car_id=grant.car_id, report_id=report["id"])

    return app
