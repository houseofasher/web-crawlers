from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import TYPE_CHECKING

from omnispider.security.rbac import Principal, Role

if TYPE_CHECKING:
    from omnispider.core.config import SecurityConfig


class ApiKeyRegistry:
    """Bearer token auth with role mapping (Nomad console session pattern)."""

    def __init__(self, config: SecurityConfig) -> None:
        self._keys: dict[str, Principal] = {}
        self._require_auth = config.require_auth
        for entry in config.api_keys:
            parts = entry.split(":", 1)
            if len(parts) != 2:
                continue
            key_hash, role_name = parts[0].strip(), parts[1].strip()
            try:
                role = Role(role_name.lower())
            except ValueError:
                role = Role.OPERATOR
            self._keys[key_hash] = Principal(subject=f"key:{role_name}", roles=[role])

    @staticmethod
    def hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode()).hexdigest()

    def resolve(self, bearer_token: str) -> Principal | None:
        token_hash = self.hash_key(bearer_token)
        return self._keys.get(token_hash)

    def verify_token(self, bearer_token: str) -> Principal | None:
        for key_hash, principal in self._keys.items():
            if hmac.compare_digest(key_hash, self.hash_key(bearer_token)):
                return principal
        return None

    @property
    def require_auth(self) -> bool:
        return self._require_auth and len(self._keys) > 0

    @staticmethod
    def generate_key(role: Role = Role.OPERATOR) -> tuple[str, str]:
        raw = secrets.token_urlsafe(32)
        return raw, f"{ApiKeyRegistry.hash_key(raw)}:{role.value}"
