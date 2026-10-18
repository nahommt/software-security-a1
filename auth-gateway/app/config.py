import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    private_key_file: str
    public_key_file: str
    db_path: str
    car_service_url: str = "http://car-service:8000"
    report_service_url: str = "http://report-service:8000"

    @classmethod
    def from_env(cls):
        return cls(
            private_key_file=os.environ.get("JWT_PRIVATE_KEY_FILE", "/run/secrets/jwt_private_key"),
            public_key_file=os.environ.get("JWT_PUBLIC_KEY_FILE", "/run/secrets/jwt_public_key"),
            db_path=os.environ.get("AUTH_DB_PATH", "/data/auth.db"),
            car_service_url=os.environ.get("CAR_SERVICE_URL", "http://car-service:8000"),
            report_service_url=os.environ.get("REPORT_SERVICE_URL", "http://report-service:8000"),
        )
