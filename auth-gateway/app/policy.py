from fastapi import HTTPException, Request, status

from app.tokens import InvalidToken

SELLER = "seller"
DEALER = "dealer"
ROLES = frozenset({SELLER, DEALER})

PUBLIC = "public"


def public(endpoint):
    endpoint.allowed_roles = PUBLIC
    return endpoint


def allow(*roles):
    unknown = set(roles) - ROLES
    if not roles or unknown:
        raise ValueError(f"invalid roles: {roles}")

    def decorator(endpoint):
        endpoint.allowed_roles = frozenset(roles)
        return endpoint

    return decorator


def _unauthorized():
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden():
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def _bearer_token(request):
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token or " " in token:
        raise _unauthorized()
    return token


async def enforce_policy(request: Request):
    allowed = getattr(request.scope.get("endpoint"), "allowed_roles", None)
    if allowed is None:
        raise _forbidden()
    if allowed == PUBLIC:
        return
    try:
        principal = request.app.state.tokens.verify_user_token(_bearer_token(request))
    except InvalidToken:
        raise _unauthorized()
    if principal.role not in ROLES or principal.role not in allowed:
        raise _forbidden()
    request.state.principal = principal


def current_principal(request: Request):
    return request.state.principal
