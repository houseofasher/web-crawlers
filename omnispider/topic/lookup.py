from __future__ import annotations

import structlog
from pydantic import BaseModel, Field

from omnispider.core.config import AppConfig
from omnispider.core.models import CrawlJobSpec, EngineType
from omnispider.core.orchestrator import Orchestrator
from omnispider.core.policy import normalize_url
from omnispider.security.nomad_stack import NomadSecurityStack
from omnispider.topic.profile import TopicProfile
from omnispider.topic.report import TopicReport, build_topic_report, format_report_text, save_report
from omnispider.topic.seeds import build_topic_seeds, enrich_seeds_from_github_search

log = structlog.get_logger()


class TopicLookupOptions(BaseModel):
    topic: str
    extra_seeds: list[str] = Field(default_factory=list)
    max_depth: int = 2
    max_pages: int = 40
    min_relevance: float = 0.12
    min_link_score: float = 0.10
    follow_waves: int = 1
    js_rendering: bool = False


class TopicLookupService:
    def __init__(self, config: AppConfig, security: NomadSecurityStack | None = None) -> None:
        self._config = config
        self._security = security

    async def run(self, options: TopicLookupOptions) -> TopicReport:
        profile = TopicProfile.parse(options.topic)
        orchestrator = Orchestrator(self._config, security=self._security)
        await orchestrator.initialize()

        try:
            seeds = build_topic_seeds(profile, options.extra_seeds)
            import httpx

            timeout = self._config.orchestrator.request_timeout_seconds
            ua = self._config.orchestrator.user_agent
            async with httpx.AsyncClient(timeout=timeout) as client:
                discovered = await enrich_seeds_from_github_search(
                    client, profile, user_agent=ua, timeout=timeout
                )
            seeds = list(dict.fromkeys(seeds + discovered))
            seeds = [normalize_url(s) for s in seeds]

            if self._security:
                blocked = self._security.ssrf_guard.validate_many(seeds)
                seeds = [s for s in seeds if s not in {b[0] for b in blocked}]

            log.info("topic_seeds", topic=profile.raw, count=len(seeds))

            spec = CrawlJobSpec(
                seeds=seeds[:20],
                engine=EngineType.AUTO,
                max_depth=options.max_depth,
                max_pages=options.max_pages,
                include_archive=False,
                include_sitemaps=False,
                js_rendering=options.js_rendering,
                topic=profile.raw,
                topic_min_link_score=options.min_link_score,
                topic_min_relevance=options.min_relevance,
                topic_follow_related=True,
            )

            job = await orchestrator.submit_job(spec)
            while True:
                current = await orchestrator.get_job(job.id)
                if current and current.status.value in ("completed", "failed", "cancelled"):
                    job = current
                    break
                import asyncio

                await asyncio.sleep(0.5)

            pages = await orchestrator.list_pages(job.id, limit=5000)
            report = build_topic_report(
                profile=profile,
                job_id=job.id,
                pages=pages,
                pages_crawled=job.pages_crawled,
                min_relevance=options.min_relevance,
            )

            # Second wave: follow high-value profile URLs discovered on relevant pages
            if options.follow_waves > 1 and report.aggregated_social_links:
                wave_seeds = [
                    u
                    for u in report.aggregated_social_links
                    if "github.com" in u or "x.com" in u or "twitter.com" in u
                ][:10]
                if wave_seeds:
                    wave_spec = CrawlJobSpec(
                        seeds=wave_seeds,
                        engine=EngineType.AUTO,
                        max_depth=1,
                        max_pages=min(20, options.max_pages),
                        include_archive=False,
                        include_sitemaps=False,
                        js_rendering=options.js_rendering,
                        topic=profile.raw,
                        topic_min_link_score=options.min_link_score,
                        topic_min_relevance=options.min_relevance,
                        topic_follow_related=True,
                    )
                    wave_job = await orchestrator.submit_job(wave_spec)
                    while True:
                        current = await orchestrator.get_job(wave_job.id)
                        if current and current.status.value in ("completed", "failed", "cancelled"):
                            break
                        import asyncio

                        await asyncio.sleep(0.5)
                    wave_pages = await orchestrator.list_pages(wave_job.id, limit=5000)
                    pages.extend(wave_pages)
                    report = build_topic_report(
                        profile=profile,
                        job_id=job.id,
                        pages=pages,
                        pages_crawled=job.pages_crawled + wave_job.pages_crawled,
                        min_relevance=options.min_relevance,
                    )

            return report
        finally:
            await orchestrator.shutdown()
