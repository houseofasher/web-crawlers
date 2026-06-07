from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class ReplayGuard:
    """Reject duplicate nonces within clock-skew window (Nomad replay guard)."""

    max_clock_skew_ms: int = 60_000
    nonce_ttl_ms: int = 120_000
    max_entries: int = 10_000
    _seen: dict[str, float] = field(default_factory=dict)

    def validate(self, nonce: str, timestamp_ms: int, correlation_id: str) -> None:
        self._purge()
        if len(self._seen) >= self.max_entries:
            oldest = next(iter(self._seen))
            del self._seen[oldest]

        now = int(time.time() * 1000)
        if timestamp_ms <= 0 or abs(now - timestamp_ms) > self.max_clock_skew_ms:
            raise ValueError("Message timestamp outside allowed clock skew window.")

        key = f"{correlation_id}:{nonce}"
        if key in self._seen:
            raise ValueError("Replay detected: duplicate nonce.")

        self._seen[key] = now + self.nonce_ttl_ms

    def _purge(self) -> None:
        now = int(time.time() * 1000)
        expired = [k for k, exp in self._seen.items() if exp <= now]
        for key in expired:
            del self._seen[key]
