import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    public_key_file: str
    db_path: str
    images_dir: str

    @classmethod
    def from_env(cls):
        return cls(
            public_key_file=os.environ.get("JWT_PUBLIC_KEY_FILE", "/run/secrets/jwt_public_key"),
            db_path=os.environ.get("CAR_DB_PATH", "/data/car.db"),
            images_dir=os.environ.get("CAR_IMAGES_DIR", "/data/images"),
        )
