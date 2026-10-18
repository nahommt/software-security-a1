import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    private_key_file: str
    public_key_file: str
    db_path: str

    @classmethod
    def from_env(cls):
        return cls(
            private_key_file=os.environ.get("JWT_PRIVATE_KEY_FILE", "/run/secrets/jwt_private_key"),
            public_key_file=os.environ.get("JWT_PUBLIC_KEY_FILE", "/run/secrets/jwt_public_key"),
            db_path=os.environ.get("AUTH_DB_PATH", "/data/auth.db"),
        )
