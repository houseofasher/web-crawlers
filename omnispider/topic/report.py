from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from omnispider.core.models import PageRecord
from omnispider.topic.extractor import extract_page_intel
from omnispider.topic.profile import TopicProfile
from omnispider.topic.scorer import is_relevant, score_page


class TopicPageIntel(BaseModel):
    url: str
    title: str | None = None
    relevance: float
    meta_description: str | None = None
    headings: list[str] = Field(default_factory=list)
    social_links: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    github_name: str | None = None
    github_bio: str | None = None
    profile_items: list[str] = Field(default_factory=list)
    snippets: list[str] = Field(default_factory=list)


class TopicReport(BaseModel):
    topic: str
    job_id: str
    pages_crawled: int
    relevant_pages: int
    pages: list[TopicPageIntel] = Field(default_factory=list)
    aggregated_social_links: list[str] = Field(default_factory=list)
    aggregated_locations: list[str] = Field(default_factory=list)
    aggregated_snippets: list[str] = Field(default_factory=list)
    related_urls: list[str] = Field(default_factory=list)


def build_topic_report(
    *,
    profile: TopicProfile,
    job_id: str,
    pages: list[PageRecord],
    pages_crawled: int,
    min_relevance: float = 0.12,
) -> TopicReport:
    intel_pages: list[TopicPageIntel] = []
    all_social: list[str] = []
    all_locations: list[str] = []
    all_snippets: list[str] = []
    related_urls: list[str] = []
    seen_urls: set[str] = set()

    for page in pages:
        if page.url in seen_urls:
            continue
        seen_urls.add(page.url)
        body = ""
        if page.content_path and Path(page.content_path).exists():
            body = Path(page.content_path).read_text(encoding="utf-8", errors="replace")

        relevance = page.metadata.get("topic_relevance")
        if relevance is None:
            relevance = score_page(url=page.url, title=page.title, body=body, profile=profile)

        if not is_relevant(relevance, min_relevance):
            continue

        raw = extract_page_intel(
            url=page.url,
            html=body,
            profile=profile,
            relevance=float(relevance),
        )
        intel = TopicPageIntel.model_validate(raw)
        intel_pages.append(intel)
        all_social.extend(
            link for link in intel.social_links if _is_valid_social_link(link)
        )
        all_locations.extend(intel.locations)
        all_snippets.extend(intel.snippets)
        related_urls.append(page.url)

    intel_pages.sort(key=lambda p: p.relevance, reverse=True)

    return TopicReport(
        topic=profile.raw,
        job_id=job_id,
        pages_crawled=pages_crawled,
        relevant_pages=len(intel_pages),
        pages=intel_pages,
        aggregated_social_links=list(dict.fromkeys(all_social)),
        aggregated_locations=list(dict.fromkeys(all_locations)),
        aggregated_snippets=list(dict.fromkeys(all_snippets))[:20],
        related_urls=list(dict.fromkeys(related_urls)),
    )


def format_report_text(report: TopicReport) -> str:
    lines = [
        f"Topic: {report.topic}",
        f"Job: {report.job_id}",
        f"Pages crawled: {report.pages_crawled} | Relevant: {report.relevant_pages}",
        "",
    ]

    if report.aggregated_social_links:
        lines.append("Social / profile links")
        for link in report.aggregated_social_links[:15]:
            lines.append(f"  - {link}")
        lines.append("")

    if report.aggregated_locations:
        lines.append("Locations mentioned")
        for loc in report.aggregated_locations[:10]:
            lines.append(f"  - {loc}")
        lines.append("")

    lines.append("Relevant pages")
    for page in report.pages[:15]:
        lines.append(f"\n[{page.relevance:.2f}] {page.url}")
        if page.title:
            lines.append(f"  Title: {page.title[:140]}")
        if page.github_name:
            lines.append(f"  GitHub name: {page.github_name}")
        if page.github_bio:
            lines.append(f"  GitHub bio: {page.github_bio[:160]}")
        for item in page.profile_items[:5]:
            lines.append(f"  - {item[:120]}")
        for snippet in page.snippets[:3]:
            lines.append(f"  > {snippet[:200]}")

    if report.aggregated_snippets:
        lines.append("\nKey snippets")
        for snippet in report.aggregated_snippets[:8]:
            lines.append(f"  > {snippet[:220]}")

    return "\n".join(lines)


def save_report(report: TopicReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.model_dump(), indent=2), encoding="utf-8")


def _is_valid_social_link(link: str) -> bool:
    lowered = link.lower()
    if any(ext in lowered for ext in (".png", ".jpg", ".svg", ".ico", "&quot")):
        return False
    if "github.com/features" in lowered or "github.com/marketplace" in lowered:
        return False
    return True
