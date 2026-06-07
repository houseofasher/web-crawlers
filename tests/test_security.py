import time

from omnispider.security.audit_log import AuditEventType, AuditLog
from omnispider.security.auth import ApiKeyRegistry
from omnispider.security.rbac import Principal, RbacPolicy, Role
from omnispider.security.replay_guard import ReplayGuard
from omnispider.security.ssrf_guard import SSRFGuard


def test_audit_chain_integrity():
    audit = AuditLog(None)
    audit.record(AuditEventType.JOB_STARTED, detail="test-1")
    audit.record(AuditEventType.JOB_COMPLETED, detail="test-2")
    valid, errors = audit.verify_chain()
    assert valid
    assert not errors


def test_rbac_operator_can_create_job():
    rbac = RbacPolicy()
    principal = Principal(subject="test", roles=[Role.OPERATOR])
    assert rbac.authorize(principal, "POST", "/v1/jobs")
    assert not rbac.authorize(None, "POST", "/v1/jobs")


def test_rbac_viewer_cannot_create_job():
    rbac = RbacPolicy()
    principal = Principal(subject="viewer", roles=[Role.VIEWER])
    assert not rbac.authorize(principal, "POST", "/v1/jobs")
    assert rbac.authorize(principal, "GET", "/health")


def test_replay_guard_rejects_duplicate_nonce():
    guard = ReplayGuard()
    ts = int(time.time() * 1000)
    guard.validate("nonce-1", ts, "corr-1")
    try:
        guard.validate("nonce-1", ts, "corr-1")
        raise AssertionError("expected replay error")
    except ValueError as exc:
        assert "Replay detected" in str(exc)


def test_ssrf_blocks_localhost():
    guard = SSRFGuard()
    ok, reason = guard.validate_url("http://127.0.0.1/admin")
    assert not ok
    assert reason in ("loopback_ip", "blocked_host")


def test_ssrf_blocks_private_ip_literal():
    guard = SSRFGuard()
    ok, reason = guard.validate_url("http://192.168.1.1/internal")
    assert not ok
    assert reason == "private_ip"


def test_ssrf_allows_public_https():
    guard = SSRFGuard()
    ok, reason = guard.validate_url("https://example.com")
    assert ok
    assert reason is None


def test_api_key_generation_and_verify():
    raw, entry = ApiKeyRegistry.generate_key(Role.ADMIN)
    key_hash = entry.split(":")[0]
    from omnispider.core.config import SecurityConfig

    registry = ApiKeyRegistry(SecurityConfig(api_keys=[entry], require_auth=True))
    principal = registry.verify_token(raw)
    assert principal is not None
    assert Role.ADMIN in principal.roles
    assert registry.verify_token("wrong-token") is None
    assert key_hash == ApiKeyRegistry.hash_key(raw)
