from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class SSRFGuard:
    """Block crawl targets that reach private/link-local/metadata networks."""

    BLOCKED_HOSTS = frozenset(
        {
            "localhost",
            "127.0.0.1",
            "0.0.0.0",
            "::1",
            "metadata.google.internal",
        }
    )

    def __init__(
        self,
        *,
        block_private_ips: bool = True,
        block_link_local: bool = True,
        allowed_schemes: list[str] | None = None,
    ) -> None:
        self._block_private = block_private_ips
        self._block_link_local = block_link_local
        self._allowed_schemes = allowed_schemes or ["http", "https"]

    def validate_url(self, url: str) -> tuple[bool, str | None]:
        parsed = urlparse(url.strip())
        if parsed.scheme not in self._allowed_schemes:
            return False, "scheme_not_allowed"
        if not parsed.hostname:
            return False, "missing_hostname"

        host = parsed.hostname.lower().rstrip(".")
        if host in self.BLOCKED_HOSTS:
            return False, "blocked_host"

        if host.endswith(".local") or host.endswith(".internal"):
            return False, "blocked_tld"

        try:
            addr_infos = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
        except socket.gaierror:
            return False, "dns_resolution_failed"

        for info in addr_infos:
            sockaddr = info[4]
            if not sockaddr:
                continue
            ip_str = sockaddr[0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                continue
            if ip.is_loopback:
                return False, "loopback_ip"
            if self._block_private and ip.is_private:
                return False, "private_ip"
            if self._block_link_local and ip.is_link_local:
                return False, "link_local_ip"
            if ip.is_multicast or ip.is_reserved:
                return False, "reserved_ip"
            if ip.is_unspecified:
                return False, "unspecified_ip"

        return True, None

    def validate_many(self, urls: list[str]) -> list[tuple[str, str]]:
        blocked: list[tuple[str, str]] = []
        for url in urls:
            ok, reason = self.validate_url(url)
            if not ok:
                blocked.append((url, reason or "blocked"))
        return blocked
