from __future__ import annotations

from omnispider.core.config import SecurityConfig


class ClientAllowlist:
    """Fail-closed API client allowlist (Nomad client allowlist pattern)."""

    def __init__(self, config: SecurityConfig) -> None:
        self._allowed = {k.strip() for k in config.client_allowlist if k.strip()}
        self._require = config.require_client_allowlist

    def is_allowed(self, client_id: str) -> bool:
        if self._require and not self._allowed:
            return False
        if not self._allowed:
            return True
        return client_id in self._allowed

    @property
    def size(self) -> int:
        return len(self._allowed)
