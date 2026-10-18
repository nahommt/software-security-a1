import json
import time
import uuid

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

JOB_SCOPES = "cars:read valuations:read reports:create"

CAR = {
    "id": 1,
    "owner": "alice",
    "make": "Volvo",
    "model": "V70",
    "year": 2015,
    "mileage": 120000,
    "description": "Test",
    "images": [],
}
VALUATIONS = [
    {
        "id": 1,
        "car_id": 1,
        "dealer": "dealer",
        "price": 85000,
        "comment": "Good condition",
        "timestamp": "2026-10-18T12:00:00+00:00",
    }
]


@pytest.fixture(scope="session")
def keys(tmp_path_factory):
    directory = tmp_path_factory.mktemp("keys")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_path = directory / "public.pem"
    public_path.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return {"private": key, "other": other, "public_path": str(public_path)}


def _sign(claims, key, drop):
    claims = {k: v for k, v in claims.items() if k not in drop}
    return jwt.encode(claims, key, algorithm="RS256")


@pytest.fixture
def service_token(keys):
    def _token(sub="alice", role="seller", scope="jobs:create", key=None, drop=(), **overrides):
        now = int(time.time())
        claims = {
            "iss": "auth-gateway",
            "aud": "report-service",
            "token_use": "service",
            "sub": sub,
            "role": role,
            "scope": scope,
            "iat": now,
            "exp": now + 60,
            "jti": uuid.uuid4().hex,
        }
        claims.update(overrides)
        return _sign(claims, key or keys["private"], drop)

    return _token


@pytest.fixture
def job_token(keys):
    def _token(sub="alice", car_id=1, job_id="job-1", scope=JOB_SCOPES, key=None, drop=(), **overrides):
        now = int(time.time())
        claims = {
            "iss": "auth-gateway",
            "aud": "car-service",
            "token_use": "job",
            "sub": sub,
            "car_id": car_id,
            "job_id": job_id,
            "scope": scope,
            "iat": now,
            "exp": now + 120,
            "jti": uuid.uuid4().hex,
        }
        claims.update(overrides)
        return _sign(claims, key or keys["private"], drop)

    return _token


class FakeCarService:
    def __init__(self):
        self.requests = []
        self.responses = {}
        self.fail_with = None

    def handler(self, request):
        self.requests.append(request)
        if self.fail_with is not None:
            raise self.fail_with
        key = (request.method, request.url.path)
        if key in self.responses:
            return httpx.Response(self.responses[key])
        if key == ("GET", "/cars/1"):
            return httpx.Response(200, json=CAR)
        if key == ("GET", "/cars/1/valuations"):
            return httpx.Response(200, json=VALUATIONS)
        if key == ("POST", "/cars/1/reports"):
            body = json.loads(request.content)
            return httpx.Response(
                201,
                json={
                    "id": 42,
                    "car_id": 1,
                    "job_id": "job-1",
                    "content": body["content"],
                    "created_at": "2026-10-18T12:00:00+00:00",
                },
            )
        return httpx.Response(404, json={"detail": "Not found"})


@pytest.fixture
def car_service():
    return FakeCarService()


@pytest.fixture
def client(keys, car_service):
    settings = Settings(public_key_file=keys["public_path"], car_service_url="http://car-service:8000")
    app = create_app(settings, transport=httpx.MockTransport(car_service.handler))
    return TestClient(app)


@pytest.fixture
def post_job(client, service_token, job_token):
    def _post(token=None, body=None):
        token = token if token is not None else service_token()
        body = body if body is not None else {"car_id": 1, "job_token": job_token()}
        return client.post("/jobs", json=body, headers={"Authorization": f"Bearer {token}"})

    return _post
