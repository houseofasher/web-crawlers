import asyncio
import re
import sys
from pathlib import Path

import aiosqlite

JOB_ID = sys.argv[1] if len(sys.argv) > 1 else "ac3935d4-af71-4ef4-bdc0-ce2865146c7f"
QUERY = "Asher Shepherd Newton Cape Coral Florida"
TERMS = ["asher", "shepherd", "newton", "cape coral", "florida", "houseofasher", "shep"]


async def main() -> None:
    async with aiosqlite.connect("data/omnispider.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT url, title, status_code, content_path FROM pages WHERE job_id=?",
            (JOB_ID,),
        ) as cur:
            rows = await cur.fetchall()

    print(f"Job: {JOB_ID}")
    print(f"Query: {QUERY}\nPages: {len(rows)}\n")

    for row in rows:
        print(f"[{row['status_code']}] {row['url']}")
        if row["title"]:
            print(f"  Title: {row['title'][:120]}")
        if row["content_path"] and Path(row["content_path"]).exists():
            body = Path(row["content_path"]).read_text(encoding="utf-8", errors="replace")
            clean = re.sub(r"\s+", " ", body)
            for term in TERMS:
                m = re.search(re.escape(term), clean, re.I)
                if m:
                    start = max(0, m.start() - 50)
                    print(f"  Hit '{term}': ...{clean[start:m.end() + 80]}...")
        print()


asyncio.run(main())
