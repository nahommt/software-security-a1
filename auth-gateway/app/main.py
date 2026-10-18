import json
import uuid
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import Settings
from app.policy import DEALER, SELLER, allow, current_principal, enforce_policy, public
from app.ratelimit import LoginRateLimiter
from app.tokens import (
    CAR_SERVICE_AUDIENCE,
    USER_TOKEN_LIFETIME,
    TokenService,
    load_private_key,
    load_public_key,
)
from app.upstream import Upstream, relay
from app.users import MAX_PASSWORD_BYTES, UserStore

REPORT_SERVICE_AUDIENCE = "report-service"
JOB_SCOPES = ["cars:read", "valuations:read", "reports:create"]
MAX_JSON_BYTES = 64 * 1024
MAX_IMAGE_BYTES = 2 * 1024 * 1024
IMAGE_ID_PATTERN = r"^[0-9a-f]{32}$"

CarId = Annotated[int, Path(ge=1)]
ReportId = Annotated[int, Path(ge=1)]
ImageId = Annotated[str, Path(pattern=IMAGE_ID_PATTERN)]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    password: str = Field(min_length=1)

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value):
        if len(value.encode()) > MAX_PASSWORD_BYTES:
            raise ValueError(f"password must be at most {MAX_PASSWORD_BYTES} bytes")
        return value


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = USER_TOKEN_LIFETIME


class Me(BaseModel):
    username: str
    role: str


async def _read_body(request, limit):
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > limit:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Request body too large")
    return bytes(data)


def _media_type(request):
    return request.headers.get("Content-Type", "").split(";")[0].strip().lower()


async def _json_body(request):
    if _media_type(request) != "application/json":
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Expected application/json")
    return await _read_body(request, MAX_JSON_BYTES)


def create_app(settings=None, login_limiter=None, car_transport=None, report_transport=None):
    settings = settings or Settings.from_env()

    app = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        dependencies=[Depends(enforce_policy)],
    )
    app.state.tokens = TokenService(
        load_private_key(settings.private_key_file),
        load_public_key(settings.public_key_file),
    )
    app.state.users = UserStore(settings.db_path)
    app.state.users.init_schema()
    app.state.login_limiter = login_limiter or LoginRateLimiter()

    tokens = app.state.tokens
    car_service = Upstream("car-service", settings.car_service_url, transport=car_transport)
    report_service = Upstream("report-service", settings.report_service_url, transport=report_transport)

    def car_token(principal, scope):
        return tokens.issue_service_token(principal, CAR_SERVICE_AUDIENCE, [scope])

    @app.post("/login", response_model=TokenResponse)
    @public
    def login(body: LoginRequest, request: Request):
        limiter = app.state.login_limiter
        client_ip = request.client.host if request.client else "unknown"
        retry_after = limiter.acquire(client_ip, body.username)
        if retry_after is not None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts",
                headers={"Retry-After": str(retry_after)},
            )
        role = app.state.users.authenticate(body.username, body.password)
        if role is None:
            limiter.record_failure(body.username)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )
        limiter.record_success(body.username)
        return TokenResponse(access_token=tokens.issue_user_token(body.username, role))

    @app.get("/me", response_model=Me)
    @allow(SELLER, DEALER)
    def me(principal=Depends(current_principal)):
        return Me(username=principal.username, role=principal.role)

    @app.post("/cars")
    @allow(SELLER)
    async def create_car(request: Request, principal=Depends(current_principal)):
        content = await _json_body(request)
        response = await run_in_threadpool(
            car_service.request,
            "POST",
            "/cars",
            car_token(principal, "cars:create"),
            content=content,
            content_type="application/json",
        )
        return relay(response)

    @app.get("/cars")
    @allow(SELLER, DEALER)
    def list_cars(
        make: Annotated[str | None, Query(min_length=1, max_length=50)] = None,
        principal=Depends(current_principal),
    ):
        params = {"make": make} if make is not None else None
        return relay(car_service.request("GET", "/cars", car_token(principal, "cars:read"), params=params))

    @app.get("/cars/{car_id}")
    @allow(SELLER, DEALER)
    def get_car(car_id: CarId, principal=Depends(current_principal)):
        return relay(car_service.request("GET", f"/cars/{car_id}", car_token(principal, "cars:read")))

    @app.post("/cars/{car_id}/images")
    @allow(SELLER)
    async def upload_image(car_id: CarId, request: Request, principal=Depends(current_principal)):
        content = await _read_body(request, MAX_IMAGE_BYTES)
        response = await run_in_threadpool(
            car_service.request,
            "POST",
            f"/cars/{car_id}/images",
            car_token(principal, "cars:create"),
            content=content,
            content_type=_media_type(request),
        )
        return relay(response)

    @app.get("/cars/{car_id}/images/{image_id}")
    @allow(SELLER, DEALER)
    def get_image(car_id: CarId, image_id: ImageId, principal=Depends(current_principal)):
        path = f"/cars/{car_id}/images/{image_id}"
        return relay(car_service.request("GET", path, car_token(principal, "cars:read")))

    @app.post("/cars/{car_id}/valuations")
    @allow(DEALER)
    async def create_valuation(car_id: CarId, request: Request, principal=Depends(current_principal)):
        content = await _json_body(request)
        response = await run_in_threadpool(
            car_service.request,
            "POST",
            f"/cars/{car_id}/valuations",
            car_token(principal, "valuations:create"),
            content=content,
            content_type="application/json",
        )
        return relay(response)

    @app.get("/cars/{car_id}/valuations")
    @allow(SELLER, DEALER)
    def list_valuations(car_id: CarId, principal=Depends(current_principal)):
        path = f"/cars/{car_id}/valuations"
        return relay(car_service.request("GET", path, car_token(principal, "valuations:read")))

    @app.post("/cars/{car_id}/reports")
    @allow(SELLER)
    def request_report(car_id: CarId, principal=Depends(current_principal)):
        check = car_service.request("GET", f"/cars/{car_id}", car_token(principal, "cars:read"))
        if check.status_code != status.HTTP_200_OK:
            return relay(check)
        job_token = tokens.issue_job_token(principal.username, car_id, uuid.uuid4().hex, JOB_SCOPES)
        service_token = tokens.issue_service_token(principal, REPORT_SERVICE_AUDIENCE, ["jobs:create"])
        return relay(
            report_service.request(
                "POST",
                "/jobs",
                service_token,
                content=json.dumps({"car_id": car_id, "job_token": job_token}).encode(),
                content_type="application/json",
            )
        )

    @app.get("/cars/{car_id}/reports")
    @allow(SELLER)
    def list_reports(car_id: CarId, principal=Depends(current_principal)):
        path = f"/cars/{car_id}/reports"
        return relay(car_service.request("GET", path, car_token(principal, "reports:read")))

    @app.get("/reports/{report_id}")
    @allow(SELLER)
    def get_report(report_id: ReportId, principal=Depends(current_principal)):
        path = f"/reports/{report_id}"
        return relay(car_service.request("GET", path, car_token(principal, "reports:read")))

    return app
