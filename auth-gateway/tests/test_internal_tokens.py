import jwt
import pytest

from app.tokens import Principal


def _decode(token, keys, audience):
    return jwt.decode(token, keys["public_pem"], algorithms=["RS256"], audience=audience)


def test_service_token_claims(app, keys):
    token = app.state.tokens.issue_service_token(Principal("alice", "seller"), "car-service", ["cars:read"])
    claims = _decode(token, keys, "car-service")
    assert claims["token_use"] == "service"
    assert claims["sub"] == "alice"
    assert claims["role"] == "seller"
    assert claims["scope"] == "cars:read"
    assert claims["exp"] - claims["iat"] == 60


def test_job_token_claims(app, keys):
    token = app.state.tokens.issue_job_token("alice", 7, "job-1", ["cars:read", "reports:create"])
    claims = _decode(token, keys, "car-service")
    assert claims["token_use"] == "job"
    assert claims["sub"] == "alice"
    assert claims["car_id"] == 7
    assert claims["job_id"] == "job-1"
    assert claims["scope"] == "cars:read reports:create"
    assert claims["exp"] - claims["iat"] == 120


@pytest.mark.parametrize("audience", ["auth-gateway", "unknown"])
def test_service_token_audience_must_be_internal_service(app, audience):
    with pytest.raises(ValueError):
        app.state.tokens.issue_service_token(Principal("alice", "seller"), audience, ["cars:read"])


def test_service_token_not_accepted_as_user_token(client, app):
    token = app.state.tokens.issue_service_token(Principal("alice", "seller"), "car-service", ["cars:read"])
    assert client.get("/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
