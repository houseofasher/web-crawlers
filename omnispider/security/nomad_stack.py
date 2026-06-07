from __future__ import annotations

from dataclasses import dataclass

from omnispider.core.config import AppConfig
from omnispider.security.audit_log import AuditLog
from omnispider.security.auth import ApiKeyRegistry
from omnispider.security.client_allowlist import ClientAllowlist
from omnispider.security.rbac import RbacPolicy
from omnispider.security.rate_limiter import DistributedRateLimiter, RateLimiter
from omnispider.security.replay_guard import ReplayGuard
from omnispider.security.ssrf_guard import SSRFGuard
from omnispider.security.vital_guard import VitalGuard


@dataclass
class NomadSecurityStack:
    audit: AuditLog
    rbac: RbacPolicy
    auth: ApiKeyRegistry
    allowlist: ClientAllowlist
    rate_limiter: RateLimiter
    distributed: DistributedRateLimiter
    replay_guard: ReplayGuard
    vital_guard: VitalGuard
    ssrf_guard: SSRFGuard


def build_security_stack(config: AppConfig) -> NomadSecurityStack:
    sec = config.security
    audit = AuditLog(sec.audit_log_dir, sec.audit_chain_key or None)
    vital = VitalGuard(audit, dev_mode=sec.dev_mode)
    vital.pulse()
    return NomadSecurityStack(
        audit=audit,
        rbac=RbacPolicy(),
        auth=ApiKeyRegistry(sec),
        allowlist=ClientAllowlist(sec),
        rate_limiter=RateLimiter(sec.max_connections, sec.max_requests_per_minute),
        distributed=DistributedRateLimiter(sec.max_requests_per_client_per_minute),
        replay_guard=ReplayGuard(
            max_clock_skew_ms=sec.replay_max_clock_skew_ms,
            nonce_ttl_ms=sec.replay_nonce_ttl_ms,
        ),
        vital_guard=vital,
        ssrf_guard=SSRFGuard(
            block_private_ips=sec.block_private_ips,
            block_link_local=sec.block_link_local,
            allowed_schemes=config.policy.allowed_schemes,
        ),
    )
