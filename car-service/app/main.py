import logging
import os
import uuid
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.authz import (
    CARS_CREATE,
    CARS_READ,
    DEALER,
    REPORTS_CREATE,
    REPORTS_READ,
    SELLER,
    VALUATIONS_CREATE,
    VALUATIONS_READ,
    can_access_car,
    current_principal,
    enforce_requirement,
    not_found,
    requires,
)
from app.config import Settings
from app.db import CarStore
from app.tokens import TokenVerifier, load_public_key

logger = logging.getLogger("car-service")

MAX_IMAGE_BYTES = 2 * 1024 * 1024
IMAGE_SIGNATURES = {
    "image/jpeg": b"\xff\xd8\xff",
    "image/png": b"\x89PNG\r\n\x1a\n",
}
IMAGE_ID_PATTERN = r"^[0-9a-f]{32}$"

CarId = Annotated[int, Path(ge=1)]


class CarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    make: str = Field(min_length=1, max_length=50)
    model: str = Field(min_length=1, max_length=50)
    year: int = Field(ge=1900, le=2100)
    mileage: int = Field(ge=0, le=2_000_000)
    description: str = Field(default="", max_length=2000)


class Car(BaseModel):
    id: int
    owner: str
    make: str
    model: str
    year: int
    mileage: int
    description: str
    images: list[str]


class ValuationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price: int = Field(ge=0, le=100_000_000)
    comment: str = Field(default="", max_length=2000)


class Valuation(BaseModel):
    id: int
    car_id: int
    dealer: str
    price: int
    comment: str
    timestamp: str


class ReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=20_000)


class Report(BaseModel):
    id: int
    car_id: int
    job_id: str
    content: str
    created_at: str


class ImageOut(BaseModel):
    id: str


def create_app(settings=None):
    settings = settings or Settings.from_env()
    logging.basicConfig(level=logging.INFO)

    app = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        dependencies=[Depends(enforce_requirement)],
    )
    app.state.verifier = TokenVerifier(load_public_key(settings.public_key_file))
    app.state.store = CarStore(settings.db_path)
    app.state.store.init_schema()
    os.makedirs(settings.images_dir, exist_ok=True)

    store = app.state.store

    def authorized_car(principal, car_id):
        car = store.get_car(car_id)
        if car is None or not can_access_car(principal, car):
            raise not_found()
        return car

    @app.post("/cars", response_model=Car, status_code=status.HTTP_201_CREATED)
    @requires(CARS_CREATE, roles=[SELLER])
    def create_car(body: CarIn, principal=Depends(current_principal)):
        return store.create_car(owner=principal.subject, **body.model_dump())

    @app.get("/cars", response_model=list[Car])
    @requires(CARS_READ, roles=[SELLER, DEALER])
    def list_cars(
        make: Annotated[str | None, Query(min_length=1, max_length=50)] = None,
        principal=Depends(current_principal),
    ):
        owner = None if principal.role == DEALER else principal.subject
        return store.list_cars(owner=owner, make=make)

    @app.get("/cars/{car_id}", response_model=Car)
    @requires(CARS_READ, roles=[SELLER, DEALER], job=True)
    def get_car(car_id: CarId, principal=Depends(current_principal)):
        if principal.role == SELLER:
            car = store.get_car(car_id)
            if car is None:
                raise not_found()
            return car
        return authorized_car(principal, car_id)

    @app.post("/cars/{car_id}/images", response_model=ImageOut, status_code=status.HTTP_201_CREATED)
    @requires(CARS_CREATE, roles=[SELLER])
    async def upload_image(car_id: CarId, request: Request, principal=Depends(current_principal)):
        authorized_car(principal, car_id)
        content_type = request.headers.get("Content-Type", "").split(";")[0].strip().lower()
        signature = IMAGE_SIGNATURES.get(content_type)
        if signature is None:
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only JPEG and PNG are allowed")

        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > MAX_IMAGE_BYTES:
                raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Image too large")
        if not data.startswith(signature):
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Content does not match type")

        image_id = uuid.uuid4().hex
        with open(os.path.join(settings.images_dir, image_id), "xb") as f:
            f.write(data)
        store.add_image(image_id, car_id, content_type)
        return ImageOut(id=image_id)

    @app.get("/cars/{car_id}/images/{image_id}")
    @requires(CARS_READ, roles=[SELLER, DEALER], job=True)
    def get_image(
        car_id: CarId,
        image_id: Annotated[str, Path(pattern=IMAGE_ID_PATTERN)],
        principal=Depends(current_principal),
    ):
        authorized_car(principal, car_id)
        image = store.get_image(car_id, image_id)
        if image is None:
            raise not_found()
        with open(os.path.join(settings.images_dir, image["id"]), "rb") as f:
            content = f.read()
        return Response(
            content=content,
            media_type=image["content_type"],
            headers={"X-Content-Type-Options": "nosniff"},
        )

    @app.post("/cars/{car_id}/valuations", response_model=Valuation, status_code=status.HTTP_201_CREATED)
    @requires(VALUATIONS_CREATE, roles=[DEALER])
    def create_valuation(car_id: CarId, body: ValuationIn, principal=Depends(current_principal)):
        authorized_car(principal, car_id)
        valuation = store.create_valuation(car_id, principal.subject, body.price, body.comment)
        logger.info("valuation %s created for car %s by dealer %s", valuation["id"], car_id, principal.subject)
        return valuation

    @app.get("/cars/{car_id}/valuations", response_model=list[Valuation])
    @requires(VALUATIONS_READ, roles=[SELLER, DEALER], job=True)
    def list_valuations(car_id: CarId, principal=Depends(current_principal)):
        authorized_car(principal, car_id)
        return store.list_valuations(car_id)

    @app.post("/cars/{car_id}/reports", response_model=Report, status_code=status.HTTP_201_CREATED)
    @requires(REPORTS_CREATE, job=True)
    def create_report(car_id: CarId, body: ReportIn, principal=Depends(current_principal)):
        authorized_car(principal, car_id)
        report = store.create_report(car_id, principal.job_id, body.content)
        if report is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Report for this job already exists")
        return report

    @app.get("/cars/{car_id}/reports", response_model=list[Report])
    @requires(REPORTS_READ, roles=[SELLER])
    def list_reports(car_id: CarId, principal=Depends(current_principal)):
        authorized_car(principal, car_id)
        return store.list_reports(car_id)

    @app.get("/reports/{report_id}", response_model=Report)
    @requires(REPORTS_READ, roles=[SELLER])
    def get_report(report_id: Annotated[int, Path(ge=1)], principal=Depends(current_principal)):
        report = store.get_report(report_id)
        if report is None:
            raise not_found()
        authorized_car(principal, report["car_id"])
        return report

    return app
