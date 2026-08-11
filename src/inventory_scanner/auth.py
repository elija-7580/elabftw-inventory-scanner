"""Optional OIDC login via Authentik (staging/production)."""

from __future__ import annotations

import os
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.types import ASGIApp

router = APIRouter(prefix="/auth", tags=["auth"])

_oauth_configured = False
_metadata: dict[str, Any] | None = None

PUBLIC_PATHS = frozenset({"/health", "/api/config/public"})
PUBLIC_PREFIXES = ("/auth/login", "/auth/callback", "/auth/logout")


def session_secret() -> str:
    secret = os.environ.get("SCANNER_SESSION_SECRET", "")
    if not secret:
        secret = os.environ.get("AUTHENTIK_SECRET_KEY", "")
    if not secret:
        raise RuntimeError("SCANNER_SESSION_SECRET required for OIDC sessions")
    return secret


def oidc_enabled() -> bool:
    return bool(
        os.environ.get("OIDC_ISSUER")
        and os.environ.get("OIDC_CLIENT_ID")
        and os.environ.get("OIDC_CLIENT_SECRET")
    )


def dev_login_enabled() -> bool:
    return os.environ.get("SCANNER_ALLOW_DEV_LOGIN", "").lower() in ("1", "true", "yes")


def is_public_path(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    if path.startswith("/js/scanner-app.") and path.endswith(".js"):
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)


def is_api_path(path: str) -> bool:
    return path.startswith("/api/")


def is_authenticated(request: Request) -> bool:
    return bool(request.session.get("user"))


def wants_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return True
    return request.url.path in ("/", "/index.html")


def _redirect_uri(request: Request) -> str:
    public = os.environ.get("ELAB_PUBLIC_URL", "https://elab.example.com").rstrip("/")
    return f"{public}/scanner/auth/callback"


def _app_redirect(path: str = "/") -> str:
    """Browser redirect path behind Caddy handle_path /scanner."""
    prefix = os.environ.get("SCANNER_URL_PREFIX", "").strip()
    if prefix:
        return f"{prefix.rstrip('/')}{path}"
    return path


def _public_base() -> str:
    return os.environ.get("ELAB_PUBLIC_URL", "https://elab.example.com").rstrip("/")


def _post_logout_redirect_uri() -> str:
    return f"{_public_base()}/scanner/auth/login?prompt=login"


def _wants_reauth(request: Request) -> bool:
    return request.query_params.get("prompt") == "login"


async def _load_metadata() -> dict[str, Any]:
    global _metadata, _oauth_configured
    issuer = os.environ.get("OIDC_ISSUER", "").rstrip("/")
    if not issuer:
        raise HTTPException(503, "OIDC not configured")
    url = f"{issuer}/.well-known/openid-configuration"
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        _metadata = r.json()
        _oauth_configured = True
        return _metadata


@router.get("/login")
async def login(request: Request) -> RedirectResponse:
    if not oidc_enabled():
        raise HTTPException(503, "OIDC not configured")
    meta = _metadata or await _load_metadata()
    state = secrets.token_urlsafe(24)
    request.session.clear()
    request.session["oidc_state"] = state
    params = {
        "client_id": os.environ["OIDC_CLIENT_ID"],
        "response_type": "code",
        "scope": "openid profile email",
        "redirect_uri": _redirect_uri(request),
        "state": state,
    }
    if _wants_reauth(request):
        params["prompt"] = "login"
    url = f"{meta['authorization_endpoint']}?{urlencode(params)}"
    return RedirectResponse(url, status_code=302)


@router.get("/callback")
async def callback(request: Request, code: str = "", state: str = "", error: str = "") -> RedirectResponse:
    if error:
        raise HTTPException(400, f"OIDC error: {error}")
    if not code:
        raise HTTPException(400, "Missing authorization code")
    expected = request.session.get("oidc_state")
    if not expected or state != expected:
        if wants_html(request):
            return RedirectResponse(_app_redirect("/auth/login"), status_code=302)
        raise HTTPException(400, "Invalid OIDC state")
    if not oidc_enabled():
        raise HTTPException(503, "OIDC not configured")
    meta = _metadata or await _load_metadata()
    token_body = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": _redirect_uri(request),
        "client_id": os.environ["OIDC_CLIENT_ID"],
        "client_secret": os.environ["OIDC_CLIENT_SECRET"],
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        tr = await client.post(meta["token_endpoint"], data=token_body)
        if tr.status_code >= 400:
            raise HTTPException(400, "Token exchange failed")
        tokens = tr.json()
        ur = await client.get(
            meta["userinfo_endpoint"],
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        ur.raise_for_status()
        userinfo = ur.json()
    id_token = tokens.get("id_token")
    request.session.clear()
    request.session["user"] = {
        "sub": userinfo.get("sub", ""),
        "email": userinfo.get("email", ""),
        "name": userinfo.get("name", userinfo.get("preferred_username", "")),
    }
    if id_token:
        request.session["id_token"] = id_token
    request.session.pop("oidc_state", None)
    return RedirectResponse(_app_redirect("/"), status_code=302)


@router.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    id_token = request.session.get("id_token")
    request.session.clear()
    fallback = RedirectResponse(_app_redirect("/auth/login?prompt=login"), status_code=302)
    fallback.delete_cookie("scanner_session")
    if not oidc_enabled():
        return fallback
    meta = _metadata or await _load_metadata()
    end_session = meta.get("end_session_endpoint")
    if not end_session:
        return fallback
    params: dict[str, str] = {
        "client_id": os.environ["OIDC_CLIENT_ID"],
        "post_logout_redirect_uri": _post_logout_redirect_uri(),
    }
    if id_token:
        params["id_token_hint"] = id_token
    response = RedirectResponse(f"{end_session}?{urlencode(params)}", status_code=302)
    response.delete_cookie("scanner_session")
    return response


@router.get("/session")
async def session_info(request: Request) -> dict[str, Any]:
    user = request.session.get("user")
    if not user:
        raise HTTPException(401, "Authentication required")
    return {"authenticated": True, "user": user}


@router.get("/dev-login")
async def dev_login(request: Request) -> RedirectResponse:
    """E2E-only session bootstrap; never enable in staging/production."""
    if not dev_login_enabled():
        raise HTTPException(404, "Not found")
    request.session.clear()
    request.session["user"] = {
        "sub": "dev-user",
        "email": "dev-login@scanner.test",
        "name": "Dev Login",
    }
    return RedirectResponse(_app_redirect("/"), status_code=302)


class RequireAuthMiddleware(BaseHTTPMiddleware):
    """Enforce server-side session for all non-public scanner routes."""

    async def dispatch(self, request: Request, call_next):
        if not oidc_enabled():
            return await call_next(request)
        path = request.url.path
        if is_public_path(path):
            return await call_next(request)
        if dev_login_enabled() and path == "/auth/dev-login":
            return await call_next(request)
        if is_authenticated(request):
            return await call_next(request)
        if is_api_path(path) or not wants_html(request):
            return JSONResponse({"detail": "Authentication required"}, status_code=401)
        return RedirectResponse(_app_redirect("/auth/login"), status_code=302)


def install_session_middleware(app: ASGIApp) -> None:
    https_only = os.environ.get("SCANNER_SESSION_HTTPS_ONLY", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    max_age = int(os.environ.get("SCANNER_SESSION_MAX_AGE", "28800"))
    app.add_middleware(
        SessionMiddleware,
        secret_key=session_secret(),
        session_cookie="scanner_session",
        max_age=max_age,
        same_site="lax",
        https_only=https_only,
    )


def install_auth_middleware(app: ASGIApp) -> None:
    if oidc_enabled():
        app.add_middleware(RequireAuthMiddleware)
        install_session_middleware(app)
