from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class OrchestratorConfig(BaseModel):
    max_concurrency: int = 16
    max_depth: int = 5
    max_pages_per_job: int = 10000
    request_timeout_seconds: int = 30
    retry_attempts: int = 3
    user_agent: str = "Omnispider/0.1"


class PolicyConfig(BaseModel):
    respect_robots_txt: bool = True
    rate_limit_per_host: float = 2.0
    allowed_schemes: list[str] = Field(default_factory=lambda: ["http", "https"])
    follow_external_links: bool = True
    blocked_domains: list[str] = Field(default_factory=list)


class EngineRoutingConfig(BaseModel):
    js_heavy: str = "playwright"
    archive: str = "archive"
    fast_discovery: str = "katana"
    forms: str = "mechanical"


class PlaywrightEngineConfig(BaseModel):
    headless: bool = True
    wait_until: str = "networkidle"


class SplashEngineConfig(BaseModel):
    base_url: str = "http://127.0.0.1:8050"


class KatanaEngineConfig(BaseModel):
    binary: str = "katana"
    extra_args: list[str] = Field(default_factory=lambda: ["-silent", "-nc"])


class EnginesConfig(BaseModel):
    default: str = "http"
    routing: EngineRoutingConfig = Field(default_factory=EngineRoutingConfig)
    playwright: PlaywrightEngineConfig = Field(default_factory=PlaywrightEngineConfig)
    splash: SplashEngineConfig = Field(default_factory=SplashEngineConfig)
    katana: KatanaEngineConfig = Field(default_factory=KatanaEngineConfig)


class DiscoveryConfig(BaseModel):
    sitemap: bool = True
    robots: bool = True
    link_extraction: bool = True
    global_seeds: list[str] = Field(default_factory=list)
    cc_tld_seeds: bool = False


class ArchiveConfig(BaseModel):
    enabled: bool = True
    wayback_cdx_url: str = "https://web.archive.org/cdx/search/cdx"
    wayback_render_url: str = "https://web.archive.org/web"
    common_crawl_index: str = "https://index.commoncrawl.org/collinfo.json"
    max_snapshots_per_url: int = 10


class StorageConfig(BaseModel):
    database_path: str = "./data/omnispider.db"
    content_dir: str = "./data/content"
    store_html: bool = True
    store_metadata: bool = True


class ApiConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8080


class SecurityConfig(BaseModel):
    enabled: bool = True
    dev_mode: bool = True
    require_auth: bool = False
    require_client_allowlist: bool = False
    client_allowlist: list[str] = Field(default_factory=list)
    api_keys: list[str] = Field(default_factory=list)
    audit_log_dir: str = "./data/audit"
    audit_chain_key: str = ""
    max_connections: int = 64
    max_requests_per_minute: int = 120
    max_requests_per_client_per_minute: int = 60
    max_body_bytes: int = 1_048_576
    replay_max_clock_skew_ms: int = 60_000
    replay_nonce_ttl_ms: int = 120_000
    block_private_ips: bool = True
    block_link_local: bool = True
    organism_pulse_seconds: int = 30


class VendorsConfig(BaseModel):
    path: str = "./vendors"


class AppConfig(BaseModel):
    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    engines: EnginesConfig = Field(default_factory=EnginesConfig)
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    archive: ArchiveConfig = Field(default_factory=ArchiveConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    vendors: VendorsConfig = Field(default_factory=VendorsConfig)


def load_config(path: str | Path | None = None) -> AppConfig:
    if path is None:
        path = Path(__file__).resolve().parents[1] / "config" / "default.yaml"
    config_path = Path(path)
    if not config_path.exists():
        return AppConfig()
    raw: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return AppConfig.model_validate(raw)
