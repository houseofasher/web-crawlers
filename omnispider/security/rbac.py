from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class Role(str, Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"
    SOVEREIGN = "sovereign"


ROLE_RANK: dict[Role, int] = {
    Role.VIEWER: 1,
    Role.OPERATOR: 2,
    Role.ADMIN: 3,
    Role.SOVEREIGN: 4,
}


class Principal(BaseModel):
    subject: str
    roles: list[Role]


class RbacPolicy:
    """Nomad gateway RBAC — route → minimum role."""

    def __init__(self) -> None:
        self._route_roles: dict[str, Role] = {
            "GET /health": Role.VIEWER,
            "GET /organism/vitals": Role.VIEWER,
            "GET /v1/engines": Role.VIEWER,
            "GET /v1/jobs": Role.OPERATOR,
            "GET /v1/jobs/{job_id}": Role.OPERATOR,
            "GET /v1/jobs/{job_id}/pages": Role.OPERATOR,
            "POST /v1/jobs": Role.OPERATOR,
            "GET /v1/audit": Role.ADMIN,
        }

    def register(self, method: str, path: str, min_role: Role) -> None:
        self._route_roles[f"{method.upper()} {path}"] = min_role

    def _match_route(self, method: str, path: str) -> Role:
        key = f"{method.upper()} {path}"
        if key in self._route_roles:
            return self._route_roles[key]
        for pattern, role in self._route_roles.items():
            _, pattern_path = pattern.split(" ", 1)
            if "{" in pattern_path:
                prefix = pattern_path.split("{")[0].rstrip("/")
                if path.startswith(prefix):
                    return role
        return Role.ADMIN

    def authorize(self, principal: Principal | None, method: str, path: str) -> bool:
        required = self._match_route(method, path)
        if not principal:
            return False
        need = ROLE_RANK[required]
        return any(ROLE_RANK[r] >= need for r in principal.roles)
