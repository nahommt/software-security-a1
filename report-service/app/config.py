import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    public_key_file: str
    car_service_url: str

    @classmethod
    def from_env(cls):
        return cls(
            public_key_file=os.environ.get("JWT_PUBLIC_KEY_FILE", "/run/secrets/jwt_public_key"),
            car_service_url=os.environ.get("CAR_SERVICE_URL", "http://car-service:8000"),
        )
