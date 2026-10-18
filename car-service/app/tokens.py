from dataclasses import dataclass

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ALGORITHM = "RS256"
ISSUER = "auth-gateway"
AUDIENCE = "car-service"
MIN_KEY_SIZE = 2048

SERVICE = "service"
JOB = "job"

BASE_CLAIMS = ["iss", "sub", "aud", "scope", "iat", "exp", "jti", "token_use"]
REQUIRED_CLAIMS = {
    SERVICE: BASE_CLAIMS + ["role"],
    JOB: BASE_CLAIMS + ["car_id", "job_id"],
}
MAX_LIFETIME = {SERVICE: 60, JOB: 120}


class InvalidToken(Exception):
    pass


@dataclass(frozen=True)
class Principal:
    kind: str
    subject: str
    scopes: frozenset
    role: str | None = None
    car_id: int | None = None
    job_id: str | None = None


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

    def verify(self, token):
        try:
            claims = jwt.decode(
                token,
                self._public_key,
                algorithms=[ALGORITHM],
                audience=AUDIENCE,
                issuer=ISSUER,
                options={"require": BASE_CLAIMS},
            )
        except jwt.PyJWTError as exc:
            raise InvalidToken() from exc

        kind = claims["token_use"]
        if kind not in REQUIRED_CLAIMS:
            raise InvalidToken()
        if any(claim not in claims for claim in REQUIRED_CLAIMS[kind]):
            raise InvalidToken()
        if claims["exp"] - claims["iat"] > MAX_LIFETIME[kind]:
            raise InvalidToken()
        if not _is_str(claims["sub"]) or not _is_str(claims["scope"]):
            raise InvalidToken()

        scopes = frozenset(claims["scope"].split())
        if kind == SERVICE:
            if not _is_str(claims["role"]):
                raise InvalidToken()
            return Principal(kind=SERVICE, subject=claims["sub"], scopes=scopes, role=claims["role"])

        car_id = claims["car_id"]
        if type(car_id) is not int or not _is_str(claims["job_id"]):
            raise InvalidToken()
        return Principal(
            kind=JOB,
            subject=claims["sub"],
            scopes=scopes,
            car_id=car_id,
            job_id=claims["job_id"],
        )
