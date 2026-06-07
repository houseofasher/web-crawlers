# Security Policy — Omnispider + Nomad Cyber Integration

Omnispider integrates the **Nomad Cyber Algorithm** security perimeter for API protection, crawl SSRF defense, and tamper-evident audit logging.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.2.x   | Yes       |

## Reporting a Vulnerability

Follow responsible disclosure. Contact the maintainers via the repositories:

- [github.com/houseofasher/web-crawlers](https://github.com/houseofasher/web-crawlers)
- [github.com/shep95/web-crawlers](https://github.com/shep95/web-crawlers)

## Security Stack

| Layer | Control |
|-------|---------|
| **Gateway Skin** | RBAC, OWASP security headers, body size limits |
| **Auth Brain** | Bearer API keys with role hierarchy |
| **Replay Nerves** | `X-Nonce` + `X-Timestamp` on state-changing requests |
| **Rate Nerves** | Connection cap + per-IP sliding window |
| **SSRF Lungs** | Block private/link-local/metadata targets in crawl seeds and frontier |
| **Audit Immune** | HMAC-chained JSONL audit log |
| **Sovereign Organism** | All organs must be vital — partial breach triggers lockdown |

## Production Checklist

```yaml
security:
  dev_mode: false
  require_auth: true
  api_keys:
    - "<sha256-hash>:admin"
  audit_chain_key: "<64-hex-chars>"
  require_client_allowlist: true
  client_allowlist:
    - "10.0.0.0/24"
  block_private_ips: true
```

Generate API keys:

```bash
omnispider security generate-key --role admin
```

## Scope

**In scope:** Omnispider API, crawl SSRF guards, audit chain, RBAC, rate limits.

**Out of scope:** Third-party crawler vendor code, target websites' security, cloud provider infrastructure.

## Safe Harbour

Good-faith security research aligned with this policy will not be pursued legally. Do not access data beyond what is necessary to demonstrate a vulnerability.
