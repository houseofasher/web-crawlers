import asyncio
import re
from pathlib import Path

import aiosqlite
from bs4 import BeautifulSoup


async def main() -> None:
    async with aiosqlite.connect("data/omnispider.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT url, title, content_path FROM pages
            WHERE url IN ('https://github.com/shep95', 'https://github.com/houseofasher')
            LIMIT 2
            """
        ) as c:
            rows = await c.fetchall()

    for row in rows:
        print("=" * 60)
        print(row["title"])
        print(row["url"])
        p = row["content_path"]
        if not p or not Path(p).exists():
            continue
        soup = BeautifulSoup(Path(p).read_text(encoding="utf-8", errors="replace"), "lxml")
        name = soup.select_one(".p-name")
        if name:
            print(f"Display name: {name.get_text(strip=True)}")
        bio = soup.select_one(".p-note")
        if bio:
            print(f"Bio: {bio.get_text(strip=True)[:200]}")
        for li in soup.select("li[itemprop]"):
            text = li.get_text(" ", strip=True)
            if text and len(text) < 150:
                print(f"  • {text}")
        full = soup.get_text(" ", strip=True)
        for phrase in ("Cape Coral", "Florida", "Asher", "Newton", "Shepherd", "shep_newton"):
            if phrase.lower() in full.lower():
                idx = full.lower().find(phrase.lower())
                print(f"  > {phrase}: ...{full[max(0, idx - 25):idx + 55]}...")


asyncio.run(main())
