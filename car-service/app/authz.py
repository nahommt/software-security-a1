from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from app.tokens import JOB, SERVICE, InvalidToken

SELLER = "seller"
DEALER = "dealer"
ROLES = frozenset({SELLER, DEALER})

CARS_CREATE = "cars:create"
CARS_READ = "cars:read"
VALUATIONS_CREATE = "valuations:create"
VALUATIONS_READ = "valuations:read"
REPORTS_CREATE = "reports:create"
REPORTS_READ = "reports:read"
SCOPES = frozenset(
    {CARS_CREATE, CARS_READ, VALUATIONS_CREATE, VALUATIONS_READ, REPORTS_CREATE, REPORTS_READ}
)


@dataclass(frozen=True)
class Requirement:
    scope: str
    roles: frozenset
    job: bool


def requires(scope, roles=(), job=False):
    if scope not in SCOPES or not set(roles) <= ROLES or not (roles or job):
        raise ValueError(f"invalid requirement: {scope} {roles} {job}")

    def decorator(endpoint):
        endpoint.requirement = Requirement(scope, frozenset(roles), job)
        return endpoint

    return decorator


def _unauthorized():
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def forbidden():
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def not_found():
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _bearer_token(request):
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token or " " in token:
        raise _unauthorized()
    return token


async def enforce_requirement(request: Request):
    requirement = getattr(request.scope.get("endpoint"), "requirement", None)
    if requirement is None:
        raise forbidden()
    try:
        principal = request.app.state.verifier.verify(_bearer_token(request))
    except InvalidToken:
        raise _unauthorized()
    if requirement.scope not in principal.scopes:
        raise forbidden()
    if principal.kind == SERVICE and principal.role not in requirement.roles:
        raise forbidden()
    if principal.kind == JOB and not requirement.job:
        raise forbidden()
    request.state.principal = principal


def current_principal(request: Request):
    return request.state.principal


def can_access_car(principal, car):
    if principal.kind == JOB:
        return car["id"] == principal.car_id and car["owner"] == principal.subject
    if principal.role == DEALER:
        return True
    return principal.role == SELLER and car["owner"] == principal.subject
