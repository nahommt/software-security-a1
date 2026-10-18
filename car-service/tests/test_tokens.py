import base64
import json
import time

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.authz import enforce_requirement, requires
from conftest import auth


def _b64(data):
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def test_missing_token_rejected(client):
    response = client.get("/cars")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_user_token_for_gateway_rejected(client, service_token):
    assert client.get("/cars", headers=auth(service_token("alice", aud="auth-gateway"))).status_code == 401


@pytest.mark.parametrize("audience", ["report-service", None])
def test_wrong_or_missing_audience_rejected(client, service_token, audience):
    assert client.get("/cars", headers=auth(service_token("alice", aud=audience))).status_code == 401


def test_wrong_issuer_rejected(client, service_token):
    assert client.get("/cars", headers=auth(service_token("alice", iss="evil"))).status_code == 401


def test_token_signed_with_other_key_rejected(client, service_token, keys):
    assert client.get("/cars", headers=auth(service_token("alice", key=keys["other"]))).status_code == 401


def test_alg_none_rejected(client):
    now = int(time.time())
    claims = {
        "iss": "auth-gateway",
        "aud": "car-service",
        "token_use": "service",
        "sub": "dealer",
        "role": "dealer",
        "scope": "cars:read",
        "iat": now,
        "exp": now + 60,
        "jti": "x",
    }
    token = f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64(claims)}."
    assert client.get("/cars", headers=auth(token)).status_code == 401


def test_expired_token_rejected(client, service_token):
    now = int(time.time())
    token = service_token("alice", iat=now - 120, exp=now - 60)
    assert client.get("/cars", headers=auth(token)).status_code == 401


def test_service_token_with_long_lifetime_rejected(client, service_token):
    now = int(time.time())
    assert client.get("/cars", headers=auth(service_token("alice", iat=now, exp=now + 61))).status_code == 401


def test_job_token_with_long_lifetime_rejected(client, make_car, job_token):
    car = make_car("alice")
    now = int(time.time())
    token = job_token("alice", car["id"], iat=now, exp=now + 121)
    assert client.get(f"/cars/{car['id']}", headers=auth(token)).status_code == 401


@pytest.mark.parametrize("token_use", [None, "user", "admin"])
def test_missing_or_unknown_token_use_rejected(client, service_token, token_use):
    assert client.get("/cars", headers=auth(service_token("alice", token_use=token_use))).status_code == 401


@pytest.mark.parametrize("claim", ["sub", "role", "scope", "iat", "exp", "jti"])
def test_service_token_missing_claim_rejected(client, service_token, claim):
    assert client.get("/cars", headers=auth(service_token("alice", **{claim: None}))).status_code == 401


@pytest.mark.parametrize("claim", ["car_id", "job_id"])
def test_job_token_missing_claim_rejected(client, make_car, job_token, claim):
    car = make_car("alice")
    token = job_token("alice", car["id"], drop=[claim])
    assert client.get(f"/cars/{car['id']}", headers=auth(token)).status_code == 401


@pytest.mark.parametrize("car_id", ["1", True, 1.0])
def test_job_token_car_id_must_be_integer(client, make_car, job_token, car_id):
    make_car("alice")
    token = job_token("alice", car_id)
    assert client.get("/cars/1", headers=auth(token)).status_code == 401


def test_service_token_cannot_become_job_token(client, make_car, service_token):
    car = make_car("alice")
    token = service_token("alice", token_use="job", scope="reports:create")
    response = client.post(f"/cars/{car['id']}/reports", json={"content": "x"}, headers=auth(token))
    assert response.status_code == 401


def test_missing_scope_denied(client, service_token):
    assert client.get("/cars", headers=auth(service_token("alice", scope="cars:create"))).status_code == 403


def test_unknown_role_denied(client, service_token):
    assert client.get("/cars", headers=auth(service_token("mallory", role="admin"))).status_code == 403


def test_dealer_role_needs_dealer_scope(client, make_car, service_token):
    car = make_car("alice")
    token = service_token("dealer", scope="cars:read")
    response = client.post(f"/cars/{car['id']}/valuations", json={"price": 1}, headers=auth(token))
    assert response.status_code == 403


def test_endpoint_without_requirement_denied(client, service_token):
    test_app = FastAPI(dependencies=[Depends(enforce_requirement)])
    test_app.state.verifier = client.app.state.verifier

    @test_app.get("/no-requirement")
    def no_requirement():
        return {"ok": True}

    @test_app.get("/with-requirement")
    @requires("cars:read", roles=["seller"])
    def with_requirement():
        return {"ok": True}

    test_client = TestClient(test_app)
    token = service_token("alice")
    assert test_client.get("/no-requirement", headers=auth(token)).status_code == 403
    assert test_client.get("/with-requirement", headers=auth(token)).status_code == 200


def test_requires_rejects_invalid_definitions():
    with pytest.raises(ValueError):
        requires("cars:delete", roles=["seller"])
    with pytest.raises(ValueError):
        requires("cars:read", roles=["admin"])
    with pytest.raises(ValueError):
        requires("cars:read")


def test_docs_not_exposed(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
