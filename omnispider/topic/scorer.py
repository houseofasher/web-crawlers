from __future__ import annotations

import re

from omnispider.topic.profile import TopicProfile

SOCIAL_DOMAINS = (
    "github.com",
    "x.com",
    "twitter.com",
    "linkedin.com",
    "instagram.com",
    "facebook.com",
    "youtube.com",
    "tiktok.com",
    "discord.gg",
    "discord.com",
)


def score_text(text: str, profile: TopicProfile) -> float:
    if not text:
        return 0.0
    lowered = text.lower()
    score = 0.0
    for phrase in profile.phrases[:6]:
        if phrase in lowered:
            score += 0.35
    hits = sum(1 for term in profile.terms if term in lowered)
    if profile.terms:
        score += min(0.55, hits / len(profile.terms) * 0.55)
    return min(1.0, score)


def score_url(url: str, profile: TopicProfile) -> float:
    lowered = url.lower()
    score = score_text(lowered, profile)
    for slug in profile.slug_variants():
        if slug in lowered:
            score += 0.25
    for domain in SOCIAL_DOMAINS:
        if domain in lowered:
            score += 0.05
    return min(1.0, score)


def score_link(url: str, anchor: str, profile: TopicProfile) -> float:
    url_score = score_url(url, profile)
    anchor_score = score_text(anchor, profile)
    combined = url_score * 0.65 + anchor_score * 0.35
    if any(domain in url.lower() for domain in SOCIAL_DOMAINS):
        combined += 0.08
    return min(1.0, combined)


def score_page(
    *,
    url: str,
    title: str | None,
    body: str,
    profile: TopicProfile,
) -> float:
    title_score = score_text(title or "", profile)
    body_score = score_text(body[:120_000], profile)
    url_score = score_url(url, profile)
    return min(1.0, title_score * 0.35 + body_score * 0.45 + url_score * 0.20)


def is_relevant(score: float, min_score: float = 0.12) -> bool:
    return score >= min_score
