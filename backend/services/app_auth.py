"""User authorization behind the authenticated Azure Static Web Apps gateway."""
from __future__ import annotations

import base64
import binascii
import json
import os
import secrets

from fastapi import HTTPException, Request
from starlette.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

FRONTEND = "https://yellow-forest-0ad79d503.6.azurestaticapps.net"
SNAPSHOT_PATHS = {"/api/mc-code/snapshot", "/api/mc-code/snapshot-file",
                  "/api/codex/snapshot", "/api/codex/snapshot-file"}


def in_cloud() -> bool:
    return bool(os.getenv("WEBSITE_SITE_NAME") or os.getenv("WEBSITE_INSTANCE_ID"))


def require_user(request: Request) -> str:
    if not in_cloud():
        if (request.client and request.client.host in {"127.0.0.1", "::1"}
                and request.url.hostname in {"localhost", "127.0.0.1", "::1"}):
            origin = request.headers.get("origin")
            local_origins = {os.getenv("FRONTEND_ORIGIN", "http://localhost:3000"),
                             "http://127.0.0.1:3000", str(request.base_url).rstrip("/")}
            if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and origin not in local_origins:
                raise HTTPException(403, "Origine locale non autorizzata")
            return "local@dev"
        raise HTTPException(403, "Lo sviluppo locale richiede una connessione da localhost")
    if (os.getenv("APP_AUTH_MODE") != "linked"
            or os.getenv("APP_AUTH_GATEWAY_ENABLED", "").lower() != "true"):
        raise HTTPException(503, "Gateway autenticato non configurato")
    # Easy Auth must require the SWA linked provider before this header is trusted.
    # Direct requests, including forged identity headers, are rejected upstream.
    try:
        raw = request.headers.get("x-ms-client-principal", "")
        if len(raw) > 32768:
            raise ValueError()
        principal = json.loads(base64.b64decode(raw, validate=True))
        email = str(principal["userDetails"]).strip().lower()
        roles = principal["userRoles"]
        if (principal["identityProvider"] != "aad" or not isinstance(roles, list)
                or "authenticated" not in roles or not principal.get("userId")):
            raise ValueError()
    except (ValueError, KeyError, TypeError, binascii.Error):
        raise HTTPException(401, "Autenticazione Entra richiesta")
    allowed_emails = {item.strip().lower() for item in os.getenv(
        "APP_ALLOWED_EMAILS", "matteo@finstat.it").split(",") if item.strip()}
    if not (email.endswith("@key-stone.it") or email in allowed_emails):
        raise HTTPException(403, "Utente non autorizzato")
    origin = request.headers.get("origin")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and origin != FRONTEND:
        raise HTTPException(403, "Origine non autorizzata")
    return email


def require_snapshot_token(request: Request) -> str:
    expected = os.getenv("MC_CODE_SNAPSHOT_TOKEN") or os.getenv("CODEX_SNAPSHOT_TOKEN")
    supplied = (request.headers.get("x-mc-code-snapshot-token")
                or request.headers.get("x-codex-snapshot-token") or "")
    if not expected or not secrets.compare_digest(supplied, expected):
        raise HTTPException(401, "Token di pubblicazione richiesto")
    return "snapshot-publisher"


def require_admin(request: Request) -> str:
    email = require_user(request)
    if not in_cloud():
        return email
    admins = {item.strip().lower() for item in os.getenv("APP_ADMIN_EMAILS", "").split(",") if item.strip()}
    if email not in admins:
        raise HTTPException(403, "Questa operazione richiede un amministratore")
    return email


class AppAuthorizationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/"):
            try:
                if request.url.path in SNAPSHOT_PATHS:
                    request.state.user = require_snapshot_token(request)
                else:
                    request.state.user = require_user(request)
            except HTTPException as exc:
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code,
                                    headers={"Cache-Control": "no-store"})
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
