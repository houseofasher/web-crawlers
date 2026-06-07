from __future__ import annotations

import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from omnispider.security.audit_log import AuditEventType, AuditLog
from omnispider.security.auth import ApiKeyRegistry
from omnispider.security.client_allowlist import ClientAllowlist
from omnispider.security.rbac import RbacPolicy, Role
from omnispider.security.rate_limiter import DistributedRateLimiter, RateLimiter
from omnispider.security.replay_guard import ReplayGuard
from omnispider.security.vital_guard import VitalGuard

SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "X-Robots-Tag": "noindex, nofollow",
}

PUBLIC_ROUTES = frozenset(
    {
        ("GET", "/health"),
        ("GET", "/organism/vitals"),
    }
)

STATE_CHANGING = frozenset({("POST", "/v1/jobs")})


class NomadSecurityMiddleware(BaseHTTPMiddleware):
    """Nomad Cyber gateway perimeter for Omnispider API."""

    def __init__(
        self,
        app,
        *,
        audit: AuditLog,
        rbac: RbacPolicy,
        auth: ApiKeyRegistry,
        allowlist: ClientAllowlist,
        rate_limiter: RateLimiter,
        distributed: DistributedRateLimiter,
        replay_guard: ReplayGuard,
        vital_guard: VitalGuard,
        max_body_bytes: int,
        dev_mode: bool,
    ) -> None:
        super().__init__(app)
        self._audit = audit
        self._rbac = rbac
        self._auth = auth
        self._allowlist = allowlist
        self._rate = rate_limiter
        self._distributed = distributed
        self._replay = replay_guard
        self._vital = vital_guard
        self._max_body = max_body_bytes
        self._dev_mode = dev_mode

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        correlation_id = request.headers.get("X-Correlation-ID") or f"gw-{uuid.uuid4().hex[:12]}"
        request.state.correlation_id = correlation_id
        client_ip = request.client.host if request.client else "unknown"
        method = request.method.upper()
        path = request.url.path
        route_key = (method, path)

        if not await self._rate.try_acquire():
            self._audit.record(
                AuditEventType.RATE_LIMIT_EXCEEDED,
                correlation_id=correlation_id,
                peer=client_ip,
                detail="gateway connection cap",
            )
            return self._json(429, {"error": "RATE_LIMITED"}, correlation_id)

        try:
            if not await self._distributed.try_acquire(client_ip):
                self._audit.record(
                    AuditEventType.RATE_LIMIT_EXCEEDED,
                    correlation_id=correlation_id,
                    peer=client_ip,
                    detail="distributed rate cap",
                )
                return self._json(429, {"error": "RATE_LIMITED"}, correlation_id)

            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > self._max_body:
                return self._json(413, {"error": "PAYLOAD_TOO_LARGE"}, correlation_id)

            if route_key not in PUBLIC_ROUTES:
                if not self._vital.is_vital():
                    self._audit.record(
                        AuditEventType.ORGANISM_LOCKDOWN,
                        correlation_id=correlation_id,
                        detail=f"{method} {path}",
                    )
                    return self._json(
                        503,
                        {
                            "error": "ORGANISM_LOCKDOWN",
                            "message": self._vital.get_vitals_report().doctrine,
                        },
                        correlation_id,
                    )

                if not self._allowlist.is_allowed(client_ip):
                    self._audit.record(
                        AuditEventType.CLIENT_REJECTED,
                        correlation_id=correlation_id,
                        peer=client_ip,
                    )
                    return self._json(403, {"error": "CLIENT_NOT_ALLOWLISTED"}, correlation_id)

                principal = None
                if self._auth.require_auth and not self._dev_mode:
                    auth_header = request.headers.get("Authorization", "")
                    if not auth_header.startswith("Bearer "):
                        self._audit.record(
                            AuditEventType.API_DENIED,
                            correlation_id=correlation_id,
                            detail="missing bearer token",
                        )
                        return self._json(401, {"error": "UNAUTHORIZED"}, correlation_id)
                    token = auth_header[7:].strip()
                    principal = self._auth.verify_token(token)
                    if not principal:
                        self._audit.record(
                            AuditEventType.API_DENIED,
                            correlation_id=correlation_id,
                            detail="invalid bearer token",
                        )
                        return self._json(401, {"error": "UNAUTHORIZED"}, correlation_id)
                    request.state.principal = principal
                elif self._dev_mode:
                    request.state.principal = None

                if not self._rbac.authorize(
                    getattr(request.state, "principal", None), method, path
                ):
                    if not self._dev_mode or self._auth.require_auth:
                        self._audit.record(
                            AuditEventType.API_DENIED,
                            correlation_id=correlation_id,
                            detail=f"rbac denied {method} {path}",
                        )
                        return self._json(403, {"error": "FORBIDDEN"}, correlation_id)

                if route_key in STATE_CHANGING:
                    nonce = request.headers.get("X-Nonce", "")
                    ts_header = request.headers.get("X-Timestamp", "")
                    if nonce and ts_header:
                        try:
                            self._replay.validate(nonce, int(ts_header), correlation_id)
                        except ValueError as exc:
                            self._audit.record(
                                AuditEventType.REPLAY_DETECTED,
                                correlation_id=correlation_id,
                                detail=str(exc),
                            )
                            return self._json(409, {"error": "REPLAY_DETECTED"}, correlation_id)

            response = await call_next(request)
            for header, value in SECURITY_HEADERS.items():
                response.headers[header] = value
            response.headers["X-Correlation-ID"] = correlation_id
            return response
        finally:
            await self._rate.release()

    @staticmethod
    def _json(status: int, body: dict, correlation_id: str) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            content=body,
            headers={**SECURITY_HEADERS, "X-Correlation-ID": correlation_id},
        )
