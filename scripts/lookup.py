"""Run a targeted lookup crawl for a search query."""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path
from urllib.parse import quote_plus, unquote

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from omnispider.core.config import load_config
from omnispider.core.models import CrawlJobSpec, EngineType
from omnispider.core.orchestrator import Orchestrator
from omnispider.security.nomad_stack import build_security_stack


async def discover_search_urls(query: str) -> list[str]:
    urls: list[str] = []
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Omnispider/0.2 (+lookup test)"},
        )
        if resp.status_code == 200:
            for match in re.findall(r"uddg=([^&\"'>]+)", resp.text):
                urls.append(unquote(match))
    return list(dict.fromkeys(urls))[:12]


async def run_lookup(query: str) -> None:
    cfg = load_config()
    security = build_security_stack(cfg) if cfg.security.enabled else None
    seeds = await discover_search_urls(query)
    if not seeds:
        print("No search result URLs discovered; using Bing fallback seed.")
        seeds = [f"https://www.bing.com/search?q={quote_plus(query)}"]

    print(f"Query: {query}")
    print(f"Seeds ({len(seeds)}):")
    for s in seeds:
        print(f"  - {s}")

    orchestrator = Orchestrator(cfg, security=security)
    await orchestrator.initialize()
    spec = CrawlJobSpec(
        seeds=seeds,
        engine=EngineType.AUTO,
        max_depth=1,
        max_pages=15,
        include_archive=False,
        include_sitemaps=False,
        js_rendering=False,
    )
    job = await orchestrator.submit_job(spec)
    print(f"\nJob {job.id} running...")

    while True:
        current = await orchestrator.get_job(job.id)
        if current and current.status.value in ("completed", "failed", "cancelled"):
            print(
                f"Done: {current.status.value} — "
                f"{current.pages_crawled} pages, {current.pages_failed} failed"
            )
            break
        await asyncio.sleep(1)

    pages = await orchestrator.list_pages(job.id, limit=50)
    keywords = [w.lower() for w in re.findall(r"\w+", query) if len(w) > 2]

    print(f"\n=== RESULTS ({len(pages)} pages) ===")
    ranked: list[tuple[int, object]] = []
    for page in pages:
        blob = f"{page.url} {page.title or ''}".lower()
        if page.content_path and Path(page.content_path).exists():
            blob += Path(page.content_path).read_bytes()[:80000].decode("utf-8", errors="replace").lower()
        hits = sum(1 for k in keywords if k in blob)
        ranked.append((hits, page))

    ranked.sort(key=lambda x: x[0], reverse=True)
    for hits, page in ranked[:10]:
        print(f"\n[{page.status_code}] keyword_hits={hits}")
        print(f"URL: {page.url}")
        if page.title:
            print(f"Title: {page.title[:140]}")
        if page.content_path and Path(page.content_path).exists():
            body = Path(page.content_path).read_bytes()[:80000].decode("utf-8", errors="replace")
            clean = re.sub(r"\s+", " ", body)
            for term in ("asher", "shepherd", "newton", "cape coral"):
                idx = clean.lower().find(term)
                if idx >= 0:
                    print(f"Match ({term}): ...{clean[max(0, idx - 30):idx + 100]}...")
                    break

    await orchestrator.shutdown()


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Asher Shepherd Newton Cape Coral Florida"
    asyncio.run(run_lookup(q))
