from dataclasses import dataclass

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ALGORITHM = "RS256"
ISSUER = "auth-gateway"
SERVICE_AUDIENCE = "report-service"
JOB_AUDIENCE = "car-service"
MIN_KEY_SIZE = 2048

SERVICE_CLAIMS = ["iss", "sub", "aud", "role", "scope", "iat", "exp", "jti", "token_use"]
JOB_CLAIMS = ["iss", "sub", "aud", "car_id", "job_id", "scope", "iat", "exp", "jti", "token_use"]
SERVICE_MAX_LIFETIME = 60
JOB_MAX_LIFETIME = 120


class InvalidToken(Exception):
    pass


@dataclass(frozen=True)
class ServicePrincipal:
    subject: str
    role: str
    scopes: frozenset


@dataclass(frozen=True)
class JobGrant:
    subject: str
    car_id: int
    job_id: str
    scopes: frozenset


def load_public_key(path):
    with open(path, "rb") as f:
        key = serialization.load_pem_public_key(f.read())
    if not isinstance(key, rsa.RSAPublicKey) or key.key_size < MIN_KEY_SIZE:
        raise ValueError("JWT verification key must be an RSA key of at least 2048 bits")
    return key


def _is_str(value):
    return isinstance(value, str) and value != ""


class TokenVerifier:
    def __init__(self, public_key):
        self._public_key = public_key

    def _decode(self, token, audience, required, token_use, max_lifetime):
        try:
            claims = jwt.decode(
                token,
                self._public_key,
                algorithms=[ALGORITHM],
                audience=audience,
                issuer=ISSUER,
                options={"require": required},
            )
        except jwt.PyJWTError as exc:
            raise InvalidToken() from exc
        if claims["token_use"] != token_use:
            raise InvalidToken()
        if claims["exp"] - claims["iat"] > max_lifetime:
            raise InvalidToken()
        if not _is_str(claims["sub"]) or not _is_str(claims["scope"]):
            raise InvalidToken()
        return claims

    def verify_service_token(self, token):
        claims = self._decode(token, SERVICE_AUDIENCE, SERVICE_CLAIMS, "service", SERVICE_MAX_LIFETIME)
        if not _is_str(claims["role"]):
            raise InvalidToken()
        return ServicePrincipal(
            subject=claims["sub"],
            role=claims["role"],
            scopes=frozenset(claims["scope"].split()),
        )

    def verify_job_token(self, token):
        claims = self._decode(token, JOB_AUDIENCE, JOB_CLAIMS, "job", JOB_MAX_LIFETIME)
        if type(claims["car_id"]) is not int or not _is_str(claims["job_id"]):
            raise InvalidToken()
        return JobGrant(
            subject=claims["sub"],
            car_id=claims["car_id"],
            job_id=claims["job_id"],
            scopes=frozenset(claims["scope"].split()),
        )
