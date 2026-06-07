from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class AuditEventType(str, Enum):
    JOB_STARTED = "job_started"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
    API_REQUEST = "api_request"
    API_DENIED = "api_denied"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    REPLAY_DETECTED = "replay_detected"
    CLIENT_REJECTED = "client_rejected_allowlist"
    SSRF_BLOCKED = "ssrf_blocked"
    ORGANISM_LOCKDOWN = "organism_lockdown"
    AUDIT_CHAIN_BREACH = "audit_chain_breach"


class AuditEvent(BaseModel):
    id: str
    ts: str
    type: AuditEventType
    correlation_id: str | None = None
    peer: str | None = None
    detail: str | None = None
    prev_entry_id: str = ""
    entry_mac: str = ""


class AuditLog:
    """Tamper-evident HMAC-chained audit log (Nomad Cyber pattern)."""

    def __init__(self, log_dir: str | Path | None, chain_key_hex: str | None = None) -> None:
        key_hex = chain_key_hex or os.environ.get("OMNISPIDER_AUDIT_CHAIN_KEY", "")
        if key_hex:
            self._chain_key = bytes.fromhex(key_hex)
        else:
            self._chain_key = secrets.token_bytes(32)
        self._entries: list[AuditEvent] = []
        self._file_path: Path | None = None
        if log_dir:
            log_path = Path(log_dir)
            log_path.mkdir(parents=True, exist_ok=True)
            self._file_path = log_path / "omnispider-audit.jsonl"
            self._load_from_disk()

    def _sign_entry(self, event: AuditEvent) -> str:
        prev_id = event.prev_entry_id or "GENESIS"
        payload = f"{event.id}|{event.ts}|{event.type.value}|{prev_id}|{event.detail or ''}"
        return hmac.new(self._chain_key, payload.encode(), hashlib.sha256).hexdigest()

    def _load_from_disk(self) -> None:
        if not self._file_path or not self._file_path.exists():
            return
        for line in self._file_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                self._entries.append(AuditEvent.model_validate(json.loads(line)))
            except Exception:
                continue

    def record(
        self,
        event_type: AuditEventType,
        *,
        correlation_id: str | None = None,
        peer: str | None = None,
        detail: str | None = None,
    ) -> AuditEvent:
        prev = self._entries[-1] if self._entries else None
        base = AuditEvent(
            id=f"{int(datetime.now(timezone.utc).timestamp() * 1000)}-{secrets.token_hex(4)}",
            ts=datetime.now(timezone.utc).isoformat(),
            type=event_type,
            correlation_id=correlation_id,
            peer=peer,
            detail=detail,
            prev_entry_id=prev.id if prev else "",
        )
        base.entry_mac = self._sign_entry(base)
        self._entries.append(base)
        if self._file_path:
            with self._file_path.open("a", encoding="utf-8") as fh:
                fh.write(base.model_dump_json() + "\n")
        return base

    def verify_chain(self) -> tuple[bool, list[str]]:
        errors: list[str] = []
        prev_id = ""
        for entry in self._entries:
            expected = self._sign_entry(
                AuditEvent(
                    id=entry.id,
                    ts=entry.ts,
                    type=entry.type,
                    correlation_id=entry.correlation_id,
                    peer=entry.peer,
                    detail=entry.detail,
                    prev_entry_id=entry.prev_entry_id,
                )
            )
            if entry.entry_mac != expected:
                errors.append(f"Entry {entry.id}: HMAC mismatch (tamper detected)")
            if entry.prev_entry_id != prev_id:
                errors.append(
                    f"Entry {entry.id}: chain broken (expected prev {prev_id}, got {entry.prev_entry_id})"
                )
            prev_id = entry.id
        return len(errors) == 0, errors

    def query(self, limit: int = 100) -> list[AuditEvent]:
        return self._entries[-limit:]

    @property
    def chain_key_hex(self) -> str:
        return self._chain_key.hex()
