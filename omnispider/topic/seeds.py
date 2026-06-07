from __future__ import annotations

import re
from urllib.parse import quote_plus, urlparse

import httpx
import structlog

from omnispider.core.policy import normalize_url
from omnispider.topic.profile import TopicProfile

log = structlog.get_logger()


LOCATION_TERMS = frozenset(
    {
        "florida", "coral", "cape", "california", "texas", "united", "states",
        "newton", "shepherd",  # too generic alone; use in phrases only
    }
)


def build_topic_seeds(profile: TopicProfile, extra_seeds: list[str] | None = None) -> list[str]:
    """Build crawlable seed URLs for a topic (avoids search engines blocked by robots.txt)."""
    seeds: list[str] = []
    q = quote_plus(profile.raw)

    seeds.extend(
        [
            f"https://github.com/search?q={q}&type=users",
            f"https://github.com/search?q={q}&type=repositories",
        ]
    )

    for slug in profile.slug_variants()[:5]:
        if "-" in slug or "_" in slug:
            seeds.append(f"https://github.com/{slug}")
            if "@" not in slug:
                seeds.append(f"https://x.com/{slug}")

    for term in profile.terms:
        if len(term) >= 5 and term.isalpha() and term not in LOCATION_TERMS:
            seeds.append(f"https://github.com/{term}")

    if extra_seeds:
        seeds.extend(extra_seeds)

    normalized = [normalize_url(s) for s in seeds]
    return list(dict.fromkeys(normalized))


async def enrich_seeds_from_github_search(
    client: httpx.AsyncClient,
    profile: TopicProfile,
    *,
    user_agent: str,
    timeout: float,
) -> list[str]:
    """Parse GitHub user search HTML for profile links matching the topic."""
    q = quote_plus(profile.raw)
    url = f"https://github.com/search?q={q}&type=users"
    found: list[str] = []
    try:
        resp = await client.get(
            url,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": user_agent},
        )
        if resp.status_code >= 400:
            return found
        for _, username in re.findall(r'href="(/([a-zA-Z0-9_-]+))"(?=[^>]*search-title)', resp.text):
            if username.lower() in ("search", "topics", "marketplace", "pricing", "login"):
                continue
            if score_username(username, profile) >= 0.1:
                found.append(normalize_url(f"https://github.com/{username}"))
        for _, username in re.findall(r'href="(/([a-zA-Z0-9_-]{2,39}))"', resp.text):
            if username.lower() in ("search", "settings", "notifications", "explore"):
                continue
            if score_username(username, profile) >= 0.2:
                found.append(normalize_url(f"https://github.com/{username}"))
    except Exception as exc:
        log.debug("github_search_seed_failed", error=str(exc))
    return list(dict.fromkeys(found))[:15]


def score_username(username: str, profile: TopicProfile) -> float:
    lowered = username.lower()
    hits = sum(1 for t in profile.terms if t in lowered)
    if hits == 0:
        return 0.0
    return min(1.0, hits / max(len(profile.terms), 1) + 0.1)


def extract_profile_urls_from_html(html: str, base_url: str, profile: TopicProfile) -> list[str]:
    """Pull outbound profile/social URLs from a page that mention the topic."""
    from omnispider.discovery.links import extract_links_with_text
    from omnispider.topic.scorer import score_link

    candidates: list[tuple[float, str]] = []
    for link, anchor in extract_links_with_text(html, base_url):
        parsed = urlparse(link)
        host = parsed.netloc.lower()
        if not any(
            d in host for d in ("github.com", "x.com", "twitter.com", "linkedin.com", "instagram.com")
        ):
            continue
        link_score = score_link(link, anchor, profile)
        if link_score >= 0.15:
            candidates.append((link_score, link))
    candidates.sort(key=lambda x: x[0], reverse=True)
    return [u for _, u in candidates[:20]]
