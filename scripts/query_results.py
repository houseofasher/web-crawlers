import asyncio
import re
from pathlib import Path

import aiosqlite

JOB_ID = "5f37d318-023a-4844-96e7-9526321dcf54"
QUERY = "Asher Shepherd Newton Cape Coral Florida"
KEYWORDS = re.findall(r"\w+", QUERY.lower())


async def main() -> None:
    async with aiosqlite.connect("data/omnispider.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT url, title, status_code, depth, content_path, links_found
            FROM pages WHERE job_id=? ORDER BY depth, fetched_at
            """,
            (JOB_ID,),
        ) as cur:
            rows = await cur.fetchall()

    print(f"Job: {JOB_ID}")
    print(f"Query: {QUERY}")
    print(f"Total pages stored: {len(rows)}\n")

    matches: list[dict] = []
    for row in rows:
        url = row["url"]
        title = row["title"] or ""
        text = f"{url} {title}".lower()
        body_snippet = ""
        content_path = row["content_path"]
        if content_path and Path(content_path).exists():
            body = Path(content_path).read_bytes()[:50000].decode("utf-8", errors="replace").lower()
            body_snippet = body
            text += " " + body

        hit_count = sum(1 for k in KEYWORDS if k in text)
        if hit_count >= 2:
            matches.append(
                {
                    "url": url,
                    "title": title,
                    "status": row["status_code"],
                    "depth": row["depth"],
                    "keyword_hits": hit_count,
                    "snippet": body_snippet[:300] if body_snippet else "",
                }
            )

    matches.sort(key=lambda x: x["keyword_hits"], reverse=True)

    print("=== TOP RELEVANCE MATCHES ===")
    if not matches:
        print("(No pages with 2+ query keyword hits — listing all crawled URLs below)\n")
        for row in rows[:15]:
            print(f"[{row['status_code']}] {row['url']}")
            if row["title"]:
                print(f"  {row['title'][:100]}")
    else:
        for m in matches[:15]:
            print(f"[{m['status']}] hits={m['keyword_hits']} depth={m['depth']}")
            print(f"  URL: {m['url']}")
            if m["title"]:
                print(f"  Title: {m['title'][:120]}")
            if m["snippet"]:
                clean = re.sub(r"\s+", " ", m["snippet"])
                idx = clean.find("asher")
                if idx == -1:
                    idx = clean.find("newton")
                if idx == -1:
                    idx = 0
                print(f"  Snippet: ...{clean[max(0, idx - 40):idx + 120]}...")
            print()

    print("=== ALL CRAWLED PAGES (summary) ===")
    for row in rows:
        print(f"[{row['status_code']}] d={row['depth']} {row['url']}")


if __name__ == "__main__":
    asyncio.run(main())
