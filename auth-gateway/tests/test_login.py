import jwt


def test_login_returns_rs256_user_token(client, passwords, keys):
    response = client.post("/login", json={"username": "alice", "password": passwords["alice"]})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 900

    token = body["access_token"]
    assert jwt.get_unverified_header(token)["alg"] == "RS256"
    claims = jwt.decode(token, keys["public_pem"], algorithms=["RS256"], audience="auth-gateway")
    assert claims["sub"] == "alice"
    assert claims["role"] == "seller"
    assert claims["aud"] == "auth-gateway"
    assert claims["exp"] - claims["iat"] == 15 * 60


def test_dealer_gets_dealer_role(login, keys):
    claims = jwt.decode(login("dealer"), keys["public_pem"], algorithms=["RS256"], audience="auth-gateway")
    assert claims["role"] == "dealer"


def test_wrong_password_rejected(client):
    response = client.post("/login", json={"username": "alice", "password": "wrong-password"})
    assert response.status_code == 401
    assert "access_token" not in response.json()


def test_unknown_user_gets_same_error_as_wrong_password(client):
    unknown = client.post("/login", json={"username": "mallory", "password": "whatever"})
    wrong = client.post("/login", json={"username": "alice", "password": "whatever"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


def test_password_of_another_user_rejected(client, passwords):
    response = client.post("/login", json={"username": "alice", "password": passwords["bob"]})
    assert response.status_code == 401


def test_password_longer_than_bcrypt_limit_rejected(client):
    response = client.post("/login", json={"username": "alice", "password": "a" * 73})
    assert response.status_code == 422


def test_role_cannot_be_set_in_login_body(client, passwords):
    response = client.post(
        "/login",
        json={"username": "alice", "password": passwords["alice"], "role": "dealer"},
    )
    assert response.status_code == 422


def test_login_requires_json_body(client):
    assert client.post("/login").status_code == 422
