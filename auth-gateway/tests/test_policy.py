import time

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.policy import DEALER, SELLER, allow, enforce_policy, public


@pytest.fixture(scope="module")
def policy_client(app):
    test_app = FastAPI(dependencies=[Depends(enforce_policy)])
    test_app.state.tokens = app.state.tokens

    @test_app.get("/dealer-only")
    @allow(DEALER)
    def dealer_only():
        return {"ok": True}

    @test_app.get("/seller-only")
    @allow(SELLER)
    def seller_only():
        return {"ok": True}

    @test_app.get("/no-policy")
    def no_policy():
        return {"ok": True}

    @test_app.get("/open")
    @public
    def open_endpoint():
        return {"ok": True}

    return TestClient(test_app)


def _get(client, path, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.get(path, headers=headers)


def test_dealer_allowed_on_dealer_endpoint(policy_client, login):
    assert _get(policy_client, "/dealer-only", login("dealer")).status_code == 200


def test_seller_denied_on_dealer_endpoint(policy_client, login):
    assert _get(policy_client, "/dealer-only", login("alice")).status_code == 403


def test_dealer_denied_on_seller_endpoint(policy_client, login):
    assert _get(policy_client, "/seller-only", login("dealer")).status_code == 403


def test_endpoint_without_policy_denied_even_with_valid_token(policy_client, login):
    assert _get(policy_client, "/no-policy", login("dealer")).status_code == 403
    assert _get(policy_client, "/no-policy").status_code == 403


def test_public_endpoint_needs_no_token(policy_client):
    assert _get(policy_client, "/open").status_code == 200


def test_unknown_role_in_valid_token_denied(policy_client, keys):
    now = int(time.time())
    claims = {
        "iss": "auth-gateway",
        "sub": "mallory",
        "aud": "auth-gateway",
        "role": "admin",
        "iat": now,
        "exp": now + 900,
        "jti": "test",
    }
    token = jwt.encode(claims, keys["private"], algorithm="RS256")
    assert _get(policy_client, "/dealer-only", token).status_code == 403
    assert _get(policy_client, "/seller-only", token).status_code == 403


def test_allow_rejects_unknown_role():
    with pytest.raises(ValueError):
        allow("admin")


def test_allow_rejects_empty_role_list():
    with pytest.raises(ValueError):
        allow()


def test_docs_and_openapi_not_exposed(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
