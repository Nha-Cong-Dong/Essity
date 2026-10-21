"""T1.9: an account whose email is not verified reaches only `/v1/me` and `/v1/auth/*`.

Rules under test, each named in its test: US-12 AC2 and A11 (any other route answers
`403 email_not_verified`; not signed in stays 401), PLAN T1.9 "Xong khi" (a business route that
forgets `verified_user` turns the route scan red), A19 (exact allow-list, router-level
dependency, no route type escapes the scan).
"""

import uuid
from collections.abc import Iterator

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute, Mount, iter_route_contexts
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from starlette.routing import BaseRoute

from core_api.api.deps import VerifiedUser, verified_user
from core_api.db.models import User
from core_api.db.session import get_session
from core_api.domain.auth.passwords import hash_password
from core_api.main import app
from core_api.repositories.auth_session import AuthSessionRepository
from core_api.repositories.user import UserRepository

PASSWORD = "ngựa vằn ăn cỏ buổi sáng"

# Reached without a verified email (A11). Exact paths: a prefix "/v1/me" would let "/v1/memos"
# through.
OPEN_PATHS = {"/healthz", "/v1/ping", "/v1/me"}
OPEN_PREFIX = "/v1/auth/"
# FastAPI's own pages, which are not APIRoutes.
DOC_PATHS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


def _depends_on(dependant: object, call: object) -> bool:
    dependencies = getattr(dependant, "dependencies", [])
    return any(dep.call is call or _depends_on(dep, call) for dep in dependencies)


def unguarded_routes(routes: list[BaseRoute]) -> list[str]:
    """Paths of routes that let an unverified account through without being meant to.

    `iter_route_contexts` (what FastAPI builds OpenAPI from) walks into included routers and
    gives each route with its router's dependencies merged in.
    """
    found: list[str] = []
    for context in iter_route_contexts(routes):
        path = context.path or repr(context.original_route)
        if not isinstance(context.original_route, APIRoute):
            if path not in DOC_PATHS:
                found.append(path)
        elif path in OPEN_PATHS or path.startswith(OPEN_PREFIX):
            continue
        elif not _depends_on(context.dependant, verified_user):
            found.append(path)
    return found


# --- The scan ---------------------------------------------------------------------------------


def test_ac2_every_business_route_rejects_unverified_account() -> None:
    assert unguarded_routes(app.routes) == []


def test_scan_flags_a_business_route_without_verified_user() -> None:
    probe = FastAPI()

    @probe.get("/v1/subjects")
    def forgot() -> None: ...

    @probe.get("/v1/memos")  # starts like /v1/me, still a business route
    def memos() -> None: ...

    assert sorted(unguarded_routes(probe.routes)) == ["/v1/memos", "/v1/subjects"]


def test_scan_accepts_verified_user_on_the_route_or_the_router() -> None:
    probe = FastAPI()
    router = APIRouter(dependencies=[Depends(verified_user)])

    @router.get("/v1/subjects")
    def on_router() -> None: ...

    @probe.get("/v1/exams")
    def on_route(user: VerifiedUser) -> None: ...

    probe.include_router(router)
    assert unguarded_routes(probe.routes) == []


def test_scan_flags_a_mount() -> None:
    probe = FastAPI()
    probe.router.routes.append(Mount("/static", app=FastAPI()))
    assert unguarded_routes(probe.routes) == ["/static"]


# --- The answers (AC2, A11) -------------------------------------------------------------------


def new_user(session: Session, *, verified: bool) -> tuple[User, str]:
    user = UserRepository(session).create(
        f"verified-{uuid.uuid4().hex[:12]}@example.com", hash_password(PASSWORD)
    )
    if verified:
        user.email_verified_at = user.created_at
    session.flush()
    token, _ = AuthSessionRepository(session).create(user.id, user.created_at)
    return user, token


@pytest.fixture
def business_client(db_session: Session) -> Iterator[TestClient]:
    probe = FastAPI()
    router = APIRouter(prefix="/v1", dependencies=[Depends(verified_user)])

    @router.get("/things")
    def things() -> dict[str, str]:
        return {"ok": "yes"}

    probe.include_router(router)

    def session_override() -> Iterator[Session]:
        yield db_session

    probe.dependency_overrides[get_session] = session_override
    yield TestClient(probe)


def test_ac2_unverified_account_gets_403_email_not_verified(
    business_client: TestClient, db_session: Session
) -> None:
    _, token = new_user(db_session, verified=False)
    response = business_client.get("/v1/things", headers={"Authorization": f"Bearer {token}"})
    assert (response.status_code, response.json()) == (403, {"detail": "email_not_verified"})


def test_verified_account_passes(business_client: TestClient, db_session: Session) -> None:
    _, token = new_user(db_session, verified=True)
    response = business_client.get("/v1/things", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


def test_not_signed_in_is_401_before_403(business_client: TestClient) -> None:
    assert business_client.get("/v1/things").status_code == 401


def test_ac2_unverified_can_call_me_and_auth_endpoints(
    client: TestClient, unverified_user: User
) -> None:
    login = client.post(
        "/v1/auth/login", json={"email": unverified_user.email, "password": PASSWORD}
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['token']}"}
    assert client.get("/v1/me", headers=headers).status_code == 200
    assert client.post("/v1/auth/logout", headers=headers).status_code == 204
