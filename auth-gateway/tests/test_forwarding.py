import json

import httpx
import jwt
import pytest
from fastapi import HTTPException

from app.upstream import Upstream

CAR = {"id": 1, "owner": "alice", "make": "Volvo", "model": "V70", "year": 2015, "mileage": 1, "description": "", "images": []}


def _claims(request, keys, audience):
    token = request.headers["Authorization"].removeprefix("Bearer ")
    return jwt.decode(token, keys["public_pem"], algorithms=["RS256"], audience=audience)


def _call(client, token, method, path, **kwargs):
    headers = {"Authorization": f"Bearer {token}", **kwargs.pop("headers", {})}
    return client.request(method, path, headers=headers, **kwargs)


ROUTES = [
    ("alice", "POST", "/cars", "/cars", "cars:create", {"json": {"make": "Volvo"}}),
    ("alice", "GET", "/cars", "/cars", "cars:read", {}),
    ("dealer", "GET", "/cars", "/cars", "cars:read", {}),
    ("alice", "GET", "/cars/1", "/cars/1", "cars:read", {}),
    ("dealer", "GET", "/cars/1", "/cars/1", "cars:read", {}),
    (
        "alice",
        "POST",
        "/cars/1/images",
        "/cars/1/images",
        "cars:create",
        {"content": b"\x89PNG\r\n\x1a\n", "headers": {"Content-Type": "image/png"}},
    ),
    ("alice", "GET", "/cars/1/images/" + "a" * 32, "/cars/1/images/" + "a" * 32, "cars:read", {}),
    ("dealer", "POST", "/cars/1/valuations", "/cars/1/valuations", "valuations:create", {"json": {"price": 1}}),
    ("alice", "GET", "/cars/1/valuations", "/cars/1/valuations", "valuations:read", {}),
    ("dealer", "GET", "/cars/1/valuations", "/cars/1/valuations", "valuations:read", {}),
    ("alice", "GET", "/cars/1/reports", "/cars/1/reports", "reports:read", {}),
    ("alice", "GET", "/reports/1", "/reports/1", "reports:read", {}),
]


@pytest.mark.parametrize("user, method, path, upstream_path, scope, kwargs", ROUTES)
def test_route_forwards_with_one_scope_service_token(
    client, login, keys, car_upstream, user, method, path, upstream_path, scope, kwargs
):
    car_upstream.set(method, upstream_path, 200, {"ok": True})
    user_token = login(user)
    response = _call(client, user_token, method, path, **kwargs)

    assert response.status_code == 200
    assert len(car_upstream.requests) == 1
    upstream = car_upstream.requests[0]
    assert (upstream.method, upstream.url.path) == (method, upstream_path)
    assert user_token not in upstream.headers["Authorization"]

    claims = _claims(upstream, keys, "car-service")
    assert claims["token_use"] == "service"
    assert claims["sub"] == user
    assert claims["scope"] == scope
    assert claims["exp"] - claims["iat"] == 60


def test_body_is_forwarded_unchanged(client, login, car_upstream):
    car_upstream.set("POST", "/cars", 201, CAR)
    body = {"make": "Volvo", "model": "V70", "year": 2015, "mileage": 1, "owner": "bob"}
    response = _call(client, login("alice"), "POST", "/cars", json=body)
    assert response.status_code == 201
    assert json.loads(car_upstream.requests[0].content) == body


def test_make_filter_is_forwarded_as_query_parameter(client, login, car_upstream):
    car_upstream.set("GET", "/cars", 200, [])
    _call(client, login("alice"), "GET", "/cars", params={"make": "' OR 1=1 --"})
    assert car_upstream.requests[0].url.params["make"] == "' OR 1=1 --"


@pytest.mark.parametrize(
    "user, method, path, kwargs",
    [
        ("dealer", "POST", "/cars", {"json": {}}),
        ("dealer", "POST", "/cars/1/images", {"content": b"x", "headers": {"Content-Type": "image/png"}}),
        ("alice", "POST", "/cars/1/valuations", {"json": {"price": 1}}),
        ("dealer", "POST", "/cars/1/reports", {}),
        ("dealer", "GET", "/cars/1/reports", {}),
        ("dealer", "GET", "/reports/1", {}),
    ],
)
def test_wrong_role_denied_before_upstream(client, login, car_upstream, report_upstream, user, method, path, kwargs):
    assert _call(client, login(user), method, path, **kwargs).status_code == 403
    assert car_upstream.requests == [] and report_upstream.requests == []


@pytest.mark.parametrize("method, path", [(m, p) for _, m, p, _, _, _ in ROUTES] + [("POST", "/cars/1/reports")])
def test_every_route_requires_token(client, car_upstream, method, path):
    assert client.request(method, path).status_code == 401
    assert car_upstream.requests == []


def test_upstream_status_and_body_are_relayed(client, login, car_upstream):
    car_upstream.set("GET", "/cars/2", 404, {"detail": "Not found"})
    response = _call(client, login("alice"), "GET", "/cars/2")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not found"}


@pytest.mark.parametrize("upstream_status", [401, 500, 503])
def test_upstream_auth_and_server_errors_become_502(client, login, car_upstream, upstream_status):
    car_upstream.set("GET", "/cars", upstream_status, {"detail": "internal detail"})
    response = _call(client, login("alice"), "GET", "/cars")
    assert response.status_code == 502
    assert "internal detail" not in response.text


def test_image_bytes_and_type_are_relayed(client, login, car_upstream):
    path = "/cars/1/images/" + "b" * 32
    car_upstream.set(
        "GET", path, 200, content=b"\x89PNG", headers={"content-type": "image/png", "x-content-type-options": "nosniff", "set-cookie": "x=1"}
    )
    response = _call(client, login("alice"), "GET", path)
    assert response.content == b"\x89PNG"
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize("image_id", ["..%2F..%2Fetc%2Fpasswd", "abc", "%2E%2E"])
def test_invalid_image_id_rejected_at_gateway(client, login, car_upstream, image_id):
    response = _call(client, login("alice"), "GET", f"/cars/1/images/{image_id}")
    assert response.status_code in (404, 422)
    assert car_upstream.requests == []


def test_oversized_image_rejected_at_gateway(client, login, car_upstream):
    content = b"\x89PNG\r\n\x1a\n" + b"\x00" * (2 * 1024 * 1024)
    response = _call(client, login("alice"), "POST", "/cars/1/images", content=content, headers={"Content-Type": "image/png"})
    assert response.status_code == 413
    assert car_upstream.requests == []


def test_oversized_json_rejected_at_gateway(client, login, car_upstream):
    response = _call(client, login("alice"), "POST", "/cars", json={"description": "x" * 70000})
    assert response.status_code == 413
    assert car_upstream.requests == []


def test_json_routes_require_json_content_type(client, login, car_upstream):
    response = _call(client, login("alice"), "POST", "/cars", content=b"make=x", headers={"Content-Type": "text/plain"})
    assert response.status_code == 415
    assert car_upstream.requests == []


def test_report_request_checks_car_then_runs_job(client, login, keys, car_upstream, report_upstream):
    car_upstream.set("GET", "/cars/1", 200, CAR)
    report_upstream.set("POST", "/jobs", 201, {"job_id": "x", "car_id": 1, "report_id": 7})

    response = _call(client, login("alice"), "POST", "/cars/1/reports")
    assert response.status_code == 201
    assert response.json()["report_id"] == 7

    check = _claims(car_upstream.requests[0], keys, "car-service")
    assert (check["sub"], check["scope"]) == ("alice", "cars:read")

    job_request = report_upstream.requests[0]
    service = _claims(job_request, keys, "report-service")
    assert service["token_use"] == "service"
    assert service["sub"] == "alice"
    assert service["scope"] == "jobs:create"
    assert service["exp"] - service["iat"] == 60

    body = json.loads(job_request.content)
    assert body["car_id"] == 1
    job = jwt.decode(body["job_token"], keys["public_pem"], algorithms=["RS256"], audience="car-service")
    assert job["token_use"] == "job"
    assert job["sub"] == "alice"
    assert job["car_id"] == 1
    assert job["scope"] == "cars:read valuations:read reports:create"
    assert job["exp"] - job["iat"] == 120


def test_each_report_request_gets_new_job_id(client, login, keys, car_upstream, report_upstream):
    car_upstream.set("GET", "/cars/1", 200, CAR)
    report_upstream.set("POST", "/jobs", 201, {"job_id": "x", "car_id": 1, "report_id": 7})
    token = login("alice")
    _call(client, token, "POST", "/cars/1/reports")
    _call(client, token, "POST", "/cars/1/reports")
    job_ids = [
        jwt.decode(json.loads(r.content)["job_token"], keys["public_pem"], algorithms=["RS256"], audience="car-service")["job_id"]
        for r in report_upstream.requests
    ]
    assert len(set(job_ids)) == 2


def test_report_request_for_foreign_car_stops_before_job(client, login, car_upstream, report_upstream):
    car_upstream.set("GET", "/cars/2", 404, {"detail": "Not found"})
    response = _call(client, login("alice"), "POST", "/cars/2/reports")
    assert response.status_code == 404
    assert report_upstream.requests == []


@pytest.mark.parametrize(
    "error, expected", [(httpx.ConnectError("down"), 502), (httpx.ReadTimeout("slow"), 504)]
)
def test_upstream_network_errors_are_mapped(error, expected):
    def fail(request):
        raise error

    upstream = Upstream("car-service", "http://car-service:8000", transport=httpx.MockTransport(fail))
    with pytest.raises(HTTPException) as exc:
        upstream.request("GET", "/cars", "token")
    assert exc.value.status_code == expected
