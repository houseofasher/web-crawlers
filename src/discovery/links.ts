import * as cheerio from "cheerio";
import { absoluteUrl } from "../core/policy.js";

export function extractLinks(html: string, baseUrl: string): string[] {
  const $ = cheerio.load(html);
  const links: string[] = [];
  $("a[href]").each((_, el) => {
    const href = $(el).attr("href");
    if (!href) return;
    const abs = absoluteUrl(baseUrl, href);
    if (abs) links.push(abs);
  });
  return [...new Set(links)];
}

export function extractLinksWithText(html: string, baseUrl: string): Array<[string, string]> {
  const $ = cheerio.load(html);
  const pairs: Array<[string, string]> = [];
  $("a[href]").each((_, el) => {
    const href = $(el).attr("href");
    if (!href) return;
    const abs = absoluteUrl(baseUrl, href);
    if (abs) pairs.push([abs, $(el).text().replace(/\s+/g, " ").trim()]);
  });
  return [...new Map(pairs).entries()].map(([u, t]) => [u, t] as [string, string]);
}

export async function discoverSitemapUrls(
  fetchFn: typeof fetch,
  seed: string,
  opts: { timeoutMs: number; userAgent: string; maxUrls?: number },
): Promise<string[]> {
  const parsed = new URL(seed);
  const candidates = [
    `${parsed.origin}/sitemap.xml`,
    `${parsed.origin}/sitemap_index.xml`,
    new URL("/sitemap.xml", seed).toString(),
  ];
  const discovered: string[] = [];
  const seen = new Set<string>();
  const queue = [...new Set(candidates)];

  while (queue.length && discovered.length < (opts.maxUrls ?? 5000)) {
    const sitemapUrl = queue.shift()!;
    if (seen.has(sitemapUrl)) continue;
    seen.add(sitemapUrl);
    try {
      const resp = await fetchFn(sitemapUrl, {
        signal: AbortSignal.timeout(opts.timeoutMs),
        headers: { "User-Agent": opts.userAgent },
      });
      if (!resp.ok) continue;
      const content = await resp.text();
      const { pages, nested } = parseSitemapXml(content);
      discovered.push(...pages);
      queue.push(...nested.filter((n) => !seen.has(n)));
    } catch {
      /* skip */
    }
  }
  return [...new Set(discovered)].slice(0, opts.maxUrls ?? 5000);
}

function parseSitemapXml(content: string): { pages: string[]; nested: string[] } {
  const pages: string[] = [];
  const nested: string[] = [];
  const $ = cheerio.load(content, { xmlMode: true });
  $("url > loc").each((_, el) => {
    const t = $(el).text().trim();
    if (t) pages.push(t);
  });
  $("sitemap > loc").each((_, el) => {
    const t = $(el).text().trim();
    if (t) nested.push(t);
  });
  return { pages, nested };
}

export async function discoverRobotsSitemaps(
  fetchFn: typeof fetch,
  seed: string,
  opts: { timeoutMs: number; userAgent: string },
): Promise<string[]> {
  const robotsUrl = `${new URL(seed).origin}/robots.txt`;
  try {
    const resp = await fetchFn(robotsUrl, {
      signal: AbortSignal.timeout(opts.timeoutMs),
      headers: { "User-Agent": opts.userAgent },
    });
    if (!resp.ok) return [];
    const text = await resp.text();
    return text
      .split("\n")
      .filter((l) => l.toLowerCase().startsWith("sitemap:"))
      .map((l) => l.split(":", 2)[1].trim())
      .filter(Boolean);
  } catch {
    return [];
  }
}
