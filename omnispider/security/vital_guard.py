from __future__ import annotations

from pydantic import BaseModel, Field

from omnispider.security.audit_log import AuditLog


class OrganState(BaseModel):
    id: str
    name: str
    state: str
    role: str
    depends_on: list[str] = Field(default_factory=list)


class OrganismVitalsReport(BaseModel):
    vital: bool
    pulse_generation: int
    organism_fingerprint: str
    lockdown_reason: str | None = None
    organs: list[OrganState] = Field(default_factory=list)
    doctrine: str = (
        "All security organs must be vital simultaneously. Partial compromise = total shutdown."
    )


class VitalGuard:
    """Nomad Sovereign Organism — interlocking security organ health checks."""

    def __init__(self, audit: AuditLog, *, dev_mode: bool = False) -> None:
        self._audit = audit
        self._dev_mode = dev_mode
        self._pulse = 1
        self._lockdown_reason: str | None = None
        self._fingerprint = audit.chain_key_hex[:16]

    def pulse(self) -> None:
        self._pulse += 1
        if self._dev_mode:
            self._lockdown_reason = None
            return
        valid, errors = self._audit.verify_chain()
        if not valid:
            self._lockdown_reason = errors[0] if errors else "audit_chain_invalid"
        else:
            self._lockdown_reason = None

    def is_vital(self) -> bool:
        if self._dev_mode:
            return True
        return self._lockdown_reason is None

    def require_vital(self, operation: str) -> None:
        if not self.is_vital():
            raise RuntimeError(
                f"ORGANISM_LOCKDOWN: {operation} blocked — {self._lockdown_reason}"
            )

    def get_vitals_report(self) -> OrganismVitalsReport:
        audit_valid, _ = self._audit.verify_chain()
        organs = [
            OrganState(
                id="audit_immune",
                name="Audit Immune System",
                state="vital" if audit_valid else "critical",
                role="Tamper-evident HMAC audit chain",
                depends_on=[],
            ),
            OrganState(
                id="gateway_skin",
                name="Gateway Skin",
                state="vital" if self.is_vital() else "critical",
                role="RBAC + rate limits + security headers",
                depends_on=["audit_immune"],
            ),
            OrganState(
                id="ssrf_lungs",
                name="SSRF Lungs",
                state="vital",
                role="Private IP / metadata endpoint blocking",
                depends_on=["audit_immune"],
            ),
            OrganState(
                id="replay_nerves",
                name="Replay Nerves",
                state="vital",
                role="Nonce + timestamp replay guard",
                depends_on=["audit_immune"],
            ),
            OrganState(
                id="auth_brain",
                name="Auth Brain",
                state="vital" if self.is_vital() else "degraded",
                role="API key RBAC perimeter",
                depends_on=["audit_immune", "gateway_skin"],
            ),
        ]
        return OrganismVitalsReport(
            vital=self.is_vital(),
            pulse_generation=self._pulse,
            organism_fingerprint=self._fingerprint,
            lockdown_reason=self._lockdown_reason,
            organs=organs,
        )
