import base64
import json
import time

import httpx
import pytest


def _b64(data):
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def test_job_fetches_car_and_valuations_and_stores_report(post_job, car_service, job_token):
    token = job_token()
    response = post_job(body={"car_id": 1, "job_token": token})

    assert response.status_code == 201
    assert response.json() == {"job_id": "job-1", "car_id": 1, "report_id": 42}

    calls = [(r.method, r.url.path) for r in car_service.requests]
    assert calls == [("GET", "/cars/1"), ("GET", "/cars/1/valuations"), ("POST", "/cars/1/reports")]
    assert all(r.headers["Authorization"] == f"Bearer {token}" for r in car_service.requests)

    content = json.loads(car_service.requests[-1].content)["content"]
    assert "Volvo V70 (2015), 120000 km" in content
    assert "85000 DKK" in content


def test_service_token_is_never_forwarded(post_job, car_service, service_token):
    token = service_token()
    post_job(token=token)
    assert all(token not in r.headers["Authorization"] for r in car_service.requests)


def test_missing_service_token_rejected(client, car_service, job_token):
    response = client.post("/jobs", json={"car_id": 1, "job_token": job_token()})
    assert response.status_code == 401
    assert car_service.requests == []


@pytest.mark.parametrize("audience", ["car-service", "auth-gateway", None])
def test_service_token_with_wrong_audience_rejected(post_job, car_service, service_token, audience):
    drop = ["aud"] if audience is None else []
    overrides = {} if audience is None else {"aud": audience}
    assert post_job(token=service_token(drop=drop, **overrides)).status_code == 401
    assert car_service.requests == []


@pytest.mark.parametrize("token_use", ["job", "user"])
def test_service_token_with_wrong_token_use_rejected(post_job, service_token, token_use):
    assert post_job(token=service_token(token_use=token_use)).status_code == 401


@pytest.mark.parametrize("claim", ["sub", "role", "scope", "iat", "exp", "jti", "token_use"])
def test_service_token_missing_claim_rejected(post_job, service_token, claim):
    assert post_job(token=service_token(drop=[claim])).status_code == 401


def test_service_token_with_long_lifetime_rejected(post_job, service_token):
    now = int(time.time())
    assert post_job(token=service_token(iat=now, exp=now + 61)).status_code == 401


def test_expired_service_token_rejected(post_job, service_token):
    now = int(time.time())
    assert post_job(token=service_token(iat=now - 120, exp=now - 60)).status_code == 401


def test_service_token_signed_with_other_key_rejected(post_job, service_token, keys):
    assert post_job(token=service_token(key=keys["other"])).status_code == 401


def test_alg_none_service_token_rejected(post_job):
    now = int(time.time())
    claims = {
        "iss": "auth-gateway",
        "aud": "report-service",
        "token_use": "service",
        "sub": "alice",
        "role": "seller",
        "scope": "jobs:create",
        "iat": now,
        "exp": now + 60,
        "jti": "x",
    }
    assert post_job(token=f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64(claims)}.").status_code == 401


def test_service_token_without_jobs_scope_denied(post_job, car_service, service_token):
    assert post_job(token=service_token(scope="cars:read")).status_code == 403
    assert car_service.requests == []


def test_dealer_cannot_create_job(post_job, car_service, service_token, job_token):
    token = service_token(sub="dealer", role="dealer")
    body = {"car_id": 1, "job_token": job_token(sub="dealer")}
    assert post_job(token=token, body=body).status_code == 403
    assert car_service.requests == []


def test_job_token_for_other_user_denied(post_job, car_service, job_token):
    assert post_job(body={"car_id": 1, "job_token": job_token(sub="bob")}).status_code == 403
    assert car_service.requests == []


def test_job_token_for_other_car_denied(post_job, car_service, job_token):
    assert post_job(body={"car_id": 1, "job_token": job_token(car_id=2)}).status_code == 403
    assert car_service.requests == []


def test_job_token_without_required_scopes_denied(post_job, car_service, job_token):
    body = {"car_id": 1, "job_token": job_token(scope="cars:read valuations:read")}
    assert post_job(body=body).status_code == 403
    assert car_service.requests == []


def test_service_token_cannot_be_used_as_job_token(post_job, car_service, service_token):
    body = {"car_id": 1, "job_token": service_token(aud="car-service")}
    assert post_job(body=body).status_code == 403
    assert car_service.requests == []


@pytest.mark.parametrize("audience", ["report-service", "auth-gateway"])
def test_job_token_with_wrong_audience_denied(post_job, car_service, job_token, audience):
    assert post_job(body={"car_id": 1, "job_token": job_token(aud=audience)}).status_code == 403
    assert car_service.requests == []


def test_job_token_with_long_lifetime_denied(post_job, job_token):
    now = int(time.time())
    assert post_job(body={"car_id": 1, "job_token": job_token(iat=now, exp=now + 121)}).status_code == 403


def test_job_token_signed_with_other_key_denied(post_job, job_token, keys):
    assert post_job(body={"car_id": 1, "job_token": job_token(key=keys["other"])}).status_code == 403


def test_garbage_job_token_denied(post_job):
    assert post_job(body={"car_id": 1, "job_token": "not-a-jwt"}).status_code == 403


def test_extra_fields_in_body_rejected(post_job, job_token):
    body = {"car_id": 1, "job_token": job_token(), "owner": "bob"}
    assert post_job(body=body).status_code == 422


@pytest.mark.parametrize(
    "car_status, expected",
    [(404, 404), (401, 403), (403, 403), (409, 409), (500, 502)],
)
def test_car_service_errors_are_mapped(post_job, car_service, car_status, expected):
    car_service.responses[("POST", "/cars/1/reports")] = car_status
    assert post_job().status_code == expected


def test_car_service_denial_stops_job_before_report(post_job, car_service):
    car_service.responses[("GET", "/cars/1")] = 404
    assert post_job().status_code == 404
    assert [(r.method, r.url.path) for r in car_service.requests] == [("GET", "/cars/1")]


def test_car_service_unreachable(post_job, car_service):
    car_service.fail_with = httpx.ConnectError("down")
    assert post_job().status_code == 502


def test_car_service_timeout(post_job, car_service):
    car_service.fail_with = httpx.ReadTimeout("slow")
    assert post_job().status_code == 504


def test_docs_not_exposed(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
