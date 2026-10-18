import time
import uuid
from dataclasses import dataclass

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ALGORITHM = "RS256"
ISSUER = "auth-gateway"
USER_TOKEN_AUDIENCE = "auth-gateway"
USER_TOKEN_LIFETIME = 15 * 60
MIN_KEY_SIZE = 2048
REQUIRED_USER_CLAIMS = ["iss", "sub", "aud", "role", "iat", "exp", "jti"]


class InvalidToken(Exception):
    pass


@dataclass(frozen=True)
class Principal:
    username: str
    role: str


def load_private_key(path):
    with open(path, "rb") as f:
        key = serialization.load_pem_private_key(f.read(), password=None)
    if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < MIN_KEY_SIZE:
        raise ValueError("JWT signing key must be an RSA key of at least 2048 bits")
    return key


def load_public_key(path):
    with open(path, "rb") as f:
        key = serialization.load_pem_public_key(f.read())
    if not isinstance(key, rsa.RSAPublicKey) or key.key_size < MIN_KEY_SIZE:
        raise ValueError("JWT verification key must be an RSA key of at least 2048 bits")
    return key


class TokenService:
    def __init__(self, private_key, public_key, clock=time.time):
        self._private_key = private_key
        self._public_key = public_key
        self._clock = clock

    def issue_user_token(self, username, role):
        now = int(self._clock())
        claims = {
            "iss": ISSUER,
            "sub": username,
            "aud": USER_TOKEN_AUDIENCE,
            "role": role,
            "iat": now,
            "exp": now + USER_TOKEN_LIFETIME,
            "jti": uuid.uuid4().hex,
        }
        return jwt.encode(claims, self._private_key, algorithm=ALGORITHM)

    def verify_user_token(self, token):
        try:
            claims = jwt.decode(
                token,
                self._public_key,
                algorithms=[ALGORITHM],
                audience=USER_TOKEN_AUDIENCE,
                issuer=ISSUER,
                options={"require": REQUIRED_USER_CLAIMS},
            )
        except jwt.PyJWTError as exc:
            raise InvalidToken() from exc
        if not isinstance(claims["sub"], str) or not isinstance(claims["role"], str):
            raise InvalidToken()
        return Principal(username=claims["sub"], role=claims["role"])
