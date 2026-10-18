import base64
import hashlib
import hmac
import json
import time

import jwt
import pytest


def _claims(**overrides):
    now = int(time.time())
    claims = {
        "iss": "auth-gateway",
        "sub": "alice",
        "aud": "auth-gateway",
        "role": "seller",
        "iat": now,
        "exp": now + 900,
        "jti": "test",
    }
    claims.update(overrides)
    return {key: value for key, value in claims.items() if value is not None}


def _b64(data):
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def _me(client, token):
    return client.get("/me", headers={"Authorization": f"Bearer {token}"})


def test_valid_token_accepted(client, login):
    response = _me(client, login("alice"))
    assert response.status_code == 200
    assert response.json() == {"username": "alice", "role": "seller"}


def test_missing_token_rejected(client):
    response = client.get("/me")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "header",
    ["", "Bearer", "Bearer ", "Basic abc", "Bearer a b", "Token abc"],
)
def test_malformed_authorization_header_rejected(client, header):
    response = client.get("/me", headers={"Authorization": header})
    assert response.status_code == 401


def test_garbage_token_rejected(client):
    assert _me(client, "not-a-jwt").status_code == 401


def test_alg_none_token_rejected(client):
    token = f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64(_claims())}."
    assert _me(client, token).status_code == 401


def test_hs256_token_signed_with_public_key_rejected(client, keys):
    header = _b64({"alg": "HS256", "typ": "JWT"})
    payload = _b64(_claims())
    signature = hmac.new(keys["public_pem"], f"{header}.{payload}".encode(), hashlib.sha256).digest()
    token = f"{header}.{payload}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"
    assert _me(client, token).status_code == 401


def test_token_signed_with_other_key_rejected(client, keys):
    token = jwt.encode(_claims(), keys["other_private"], algorithm="RS256")
    assert _me(client, token).status_code == 401


def test_tampered_payload_rejected(client, login):
    header, _, signature = login("alice").split(".")
    forged = f"{header}.{_b64(_claims(role='dealer'))}.{signature}"
    assert _me(client, forged).status_code == 401


def test_expired_token_rejected(client, keys):
    now = int(time.time())
    token = jwt.encode(_claims(iat=now - 1000, exp=now - 100), keys["private"], algorithm="RS256")
    assert _me(client, token).status_code == 401


@pytest.mark.parametrize("audience", ["car-service", "report-service", None])
def test_wrong_or_missing_audience_rejected(client, keys, audience):
    token = jwt.encode(_claims(aud=audience), keys["private"], algorithm="RS256")
    assert _me(client, token).status_code == 401


@pytest.mark.parametrize("claim", ["iss", "sub", "role", "iat", "exp", "jti"])
def test_token_missing_required_claim_rejected(client, keys, claim):
    token = jwt.encode(_claims(**{claim: None}), keys["private"], algorithm="RS256")
    assert _me(client, token).status_code == 401


def test_wrong_issuer_rejected(client, keys):
    token = jwt.encode(_claims(iss="someone-else"), keys["private"], algorithm="RS256")
    assert _me(client, token).status_code == 401
