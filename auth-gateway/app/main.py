from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import Settings
from app.policy import DEALER, SELLER, allow, current_principal, enforce_policy, public
from app.tokens import USER_TOKEN_LIFETIME, TokenService, load_private_key, load_public_key
from app.users import MAX_PASSWORD_BYTES, UserStore


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    password: str = Field(min_length=1)

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value):
        if len(value.encode()) > MAX_PASSWORD_BYTES:
            raise ValueError(f"password must be at most {MAX_PASSWORD_BYTES} bytes")
        return value


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = USER_TOKEN_LIFETIME


class Me(BaseModel):
    username: str
    role: str


def create_app(settings=None):
    settings = settings or Settings.from_env()

    app = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        dependencies=[Depends(enforce_policy)],
    )
    app.state.tokens = TokenService(
        load_private_key(settings.private_key_file),
        load_public_key(settings.public_key_file),
    )
    app.state.users = UserStore(settings.db_path)
    app.state.users.init_schema()

    @app.post("/login", response_model=TokenResponse)
    @public
    def login(body: LoginRequest):
        role = app.state.users.authenticate(body.username, body.password)
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )
        return TokenResponse(access_token=app.state.tokens.issue_user_token(body.username, role))

    @app.get("/me", response_model=Me)
    @allow(SELLER, DEALER)
    def me(principal=Depends(current_principal)):
        return Me(username=principal.username, role=principal.role)

    return app
