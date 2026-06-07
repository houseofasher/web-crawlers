from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from omnispider.topic.profile import TopicProfile
from omnispider.topic.scorer import score_text

LOCATION_RE = re.compile(
    r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*,\s*(?:[A-Z]{2}|Florida|California|Texas|[A-Z][a-z]+))\b"
)
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
SOCIAL_RE = re.compile(
    r"https?://(?:www\.)?(?:github\.com/(?![^/]*\.(?:png|jpg|svg|ico))[^/\s\"'<>]+|"
    r"x\.com/[^\s\"'<>]+|twitter\.com/[^\s\"'<>]+|"
    r"linkedin\.com/in/[^\s\"'<>]+|instagram\.com/[^\s\"'<>]+|"
    r"facebook\.com/[^\s\"'<>]+|discord\.gg/[^\s\"'<>]+)",
    re.I,
)


def _snippets_around_terms(text: str, profile: TopicProfile, max_snippets: int = 8) -> list[str]:
    snippets: list[str] = []
    lowered = text.lower()
    for term in profile.terms:
        if len(term) < 3:
            continue
        start = 0
        while len(snippets) < max_snippets:
            idx = lowered.find(term, start)
            if idx < 0:
                break
            snippet = text[max(0, idx - 80) : idx + len(term) + 120]
            snippet = re.sub(r"\s+", " ", snippet).strip()
            if snippet and snippet not in snippets:
                snippets.append(snippet)
            start = idx + len(term)
    return snippets[:max_snippets]


def extract_page_intel(
    *,
    url: str,
    html: str,
    profile: TopicProfile,
    relevance: float,
) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    title = soup.title.get_text(strip=True) if soup.title else None
    text = soup.get_text(" ", strip=True)

    meta_desc = ""
    desc_tag = soup.find("meta", attrs={"name": "description"})
    if desc_tag and desc_tag.get("content"):
        meta_desc = desc_tag["content"].strip()
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        meta_desc = meta_desc or og_desc["content"].strip()

    headings = [
        h.get_text(" ", strip=True)
        for h in soup.find_all(["h1", "h2", "h3"])
        if h.get_text(strip=True)
    ][:10]

    social_links = list(dict.fromkeys(SOCIAL_RE.findall(html)))[:15]
    locations = list(dict.fromkeys(LOCATION_RE.findall(text)))[:10]
    emails = list(dict.fromkeys(EMAIL_RE.findall(text)))[:5]

    # GitHub-specific fields
    github_name = None
    github_bio = None
    if "github.com" in url:
        name_el = soup.select_one(".p-name")
        bio_el = soup.select_one(".p-note")
        if name_el:
            github_name = name_el.get_text(strip=True)
        if bio_el:
            github_bio = bio_el.get_text(strip=True)

    profile_items: list[str] = []
    for li in soup.select("li[itemprop]"):
        item = li.get_text(" ", strip=True)
        if item and len(item) < 200 and score_text(item, profile) > 0:
            profile_items.append(item)

    return {
        "url": url,
        "title": title,
        "relevance": round(relevance, 3),
        "meta_description": meta_desc or None,
        "headings": headings,
        "social_links": social_links,
        "locations": locations,
        "emails": emails,
        "github_name": github_name,
        "github_bio": github_bio,
        "profile_items": profile_items,
        "snippets": _snippets_around_terms(text, profile),
    }
