import type { TopicPageIntel, TopicReport, PageRecord } from "../core/models.js";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import * as cheerio from "cheerio";

const STOPWORDS = new Set(["a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "about"]);
const LOCATION_TERMS = new Set([
  "florida", "coral", "cape", "california", "texas", "united", "states", "newton", "shepherd",
]);
const SOCIAL_DOMAINS = ["github.com", "x.com", "twitter.com", "linkedin.com", "instagram.com", "discord.gg"];

export class TopicProfile {
  readonly raw: string;
  readonly terms: string[];
  readonly phrases: string[];
  readonly primary: string;

  private constructor(raw: string, terms: string[], phrases: string[], primary: string) {
    this.raw = raw;
    this.terms = terms;
    this.phrases = phrases;
    this.primary = primary;
  }

  static parse(query: string): TopicProfile {
    const raw = query.trim();
    if (!raw) throw new Error("Topic query cannot be empty");
    const terms = [
      ...new Set(
        (raw.match(/[a-zA-Z0-9_@.-]+/g) ?? [])
          .filter((t) => t.length > 1 && !STOPWORDS.has(t.toLowerCase()))
          .map((t) => t.toLowerCase()),
      ),
    ];
    const words = raw.split(/\s+/);
    const phrases: string[] = [];
    for (const size of [4, 3, 2]) {
      for (let i = 0; i <= words.length - size; i++) {
        const phrase = words.slice(i, i + size).join(" ").trim().toLowerCase();
        if (phrase.length > 4) phrases.push(phrase);
      }
    }
    const uniquePhrases = [...new Set(phrases)];
    return new TopicProfile(raw, terms, uniquePhrases, uniquePhrases[0] ?? terms[0] ?? raw.toLowerCase());
  }

  slugVariants(): string[] {
    const slugs: string[] = [];
    if (this.terms.length >= 2) {
      slugs.push(this.terms.slice(0, 2).join("-"));
      slugs.push(this.terms.slice(0, 3).join("-"));
      slugs.push(this.terms.slice(0, 2).join("_"));
    }
    for (const t of this.terms) if (t.length > 3) slugs.push(t);
    return [...new Set(slugs)];
  }
}

export function scoreText(text: string, profile: TopicProfile): number {
  if (!text) return 0;
  const lowered = text.toLowerCase();
  let score = 0;
  for (const phrase of profile.phrases.slice(0, 6)) {
    if (lowered.includes(phrase)) score += 0.35;
  }
  const hits = profile.terms.filter((t) => lowered.includes(t)).length;
  if (profile.terms.length) score += Math.min(0.55, (hits / profile.terms.length) * 0.55);
  return Math.min(1, score);
}

export function scoreUrl(url: string, profile: TopicProfile): number {
  let score = scoreText(url.toLowerCase(), profile);
  for (const slug of profile.slugVariants()) if (url.toLowerCase().includes(slug)) score += 0.25;
  for (const d of SOCIAL_DOMAINS) if (url.includes(d)) score += 0.05;
  return Math.min(1, score);
}

export function scoreLink(url: string, anchor: string, profile: TopicProfile): number {
  const combined = scoreUrl(url, profile) * 0.65 + scoreText(anchor, profile) * 0.35;
  return Math.min(1, combined + (SOCIAL_DOMAINS.some((d) => url.includes(d)) ? 0.08 : 0));
}

export function scorePage(url: string, title: string | null | undefined, body: string, profile: TopicProfile): number {
  return Math.min(
    1,
    scoreText(title ?? "", profile) * 0.35 +
      scoreText(body.slice(0, 120000), profile) * 0.45 +
      scoreUrl(url, profile) * 0.2,
  );
}

export function buildTopicSeeds(profile: TopicProfile, extraSeeds: string[] = []): string[] {
  const q = encodeURIComponent(profile.raw);
  const seeds = [
    `https://github.com/search?q=${q}&type=users`,
    `https://github.com/search?q=${q}&type=repositories`,
  ];
  for (const slug of profile.slugVariants().slice(0, 5)) {
    if (slug.includes("-") || slug.includes("_")) {
      seeds.push(`https://github.com/${slug}`);
      seeds.push(`https://x.com/${slug}`);
    }
  }
  for (const term of profile.terms) {
    if (term.length >= 5 && /^[a-z]+$/i.test(term) && !LOCATION_TERMS.has(term)) {
      seeds.push(`https://github.com/${term}`);
    }
  }
  seeds.push(...extraSeeds);
  return [...new Set(seeds.map((s) => new URL(s).toString()))];
}

export async function enrichSeedsFromGithubSearch(
  profile: TopicProfile,
  opts: { userAgent: string; timeoutMs: number },
): Promise<string[]> {
  const q = encodeURIComponent(profile.raw);
  const url = `https://github.com/search?q=${q}&type=users`;
  const found: string[] = [];
  try {
    const resp = await fetch(url, {
      signal: AbortSignal.timeout(opts.timeoutMs),
      headers: { "User-Agent": opts.userAgent },
    });
    if (!resp.ok) return found;
    const html = await resp.text();
    const re = /href="\/([a-zA-Z0-9_-]{2,39})"/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(html))) {
      const username = m[1];
      if (["search", "settings", "explore", "login", "pricing"].includes(username.toLowerCase())) continue;
      const hits = profile.terms.filter((t) => username.toLowerCase().includes(t)).length;
      if (hits > 0) found.push(`https://github.com/${username}`);
    }
  } catch {
    /* skip */
  }
  return [...new Set(found)].slice(0, 15);
}

export function extractProfileUrlsFromHtml(html: string, baseUrl: string, profile: TopicProfile): string[] {
  const $ = cheerio.load(html);
  const candidates: Array<[number, string]> = [];
  $("a[href]").each((_, el) => {
    const href = $(el).attr("href");
    if (!href) return;
    try {
      const link = new URL(href, baseUrl).toString();
      const host = new URL(link).hostname;
      if (!SOCIAL_DOMAINS.some((d) => host.includes(d))) return;
      const anchor = $(el).text().replace(/\s+/g, " ").trim();
      const s = scoreLink(link, anchor, profile);
      if (s >= 0.15) candidates.push([s, link]);
    } catch {
      /* skip */
    }
  });
  candidates.sort((a, b) => b[0] - a[0]);
  return [...new Set(candidates.map((c) => c[1]))].slice(0, 20);
}

function isValidSocialLink(link: string): boolean {
  const l = link.toLowerCase();
  if (/\.(png|jpg|svg|ico)|&quot/.test(l)) return false;
  if (l.includes("github.com/features") || l.includes("github.com/marketplace")) return false;
  return true;
}

export function extractPageIntel(
  url: string,
  html: string,
  profile: TopicProfile,
  relevance: number,
): TopicPageIntel {
  const $ = cheerio.load(html);
  $("script, style, noscript").remove();
  const title = $("title").first().text().trim() || null;
  const text = $.root().text().replace(/\s+/g, " ");
  const metaDesc =
    $('meta[name="description"]').attr("content")?.trim() ||
    $('meta[property="og:description"]').attr("content")?.trim() ||
    null;
  const headings = ["h1", "h2", "h3"]
    .flatMap((tag) => $(tag).map((_, el) => $(el).text().trim()).get())
    .filter(Boolean)
    .slice(0, 10);
  const socialLinks = [
    ...new Set(
      (html.match(
        /https?:\/\/(?:www\.)?(?:github\.com\/(?!.*\.(?:png|jpg|svg))[^/\s"'<>]+|x\.com\/[^\s"'<>]+|twitter\.com\/[^\s"'<>]+|linkedin\.com\/in\/[^\s"'<>]+|discord\.gg\/[^\s"'<>]+)/gi,
      ) ?? []).filter(isValidSocialLink),
    ),
  ].slice(0, 15);
  let githubName: string | null = null;
  let githubBio: string | null = null;
  if (url.includes("github.com")) {
    githubName = $(".p-name").first().text().trim() || null;
    githubBio = $(".p-note").first().text().trim() || null;
  }
  const profileItems = $("li[itemprop]")
    .map((_, el) => $(el).text().replace(/\s+/g, " ").trim())
    .get()
    .filter((t) => t.length < 200 && scoreText(t, profile) > 0)
    .slice(0, 8);
  const snippets: string[] = [];
  for (const term of profile.terms) {
    if (term.length < 3) continue;
    let idx = text.toLowerCase().indexOf(term);
    while (idx >= 0 && snippets.length < 8) {
      snippets.push(text.slice(Math.max(0, idx - 80), idx + term.length + 120).trim());
      idx = text.toLowerCase().indexOf(term, idx + term.length);
    }
  }
  return {
    url,
    title,
    relevance: Math.round(relevance * 1000) / 1000,
    metaDescription: metaDesc,
    headings,
    socialLinks,
    locations: [],
    emails: [],
    githubName,
    githubBio,
    profileItems,
    snippets: [...new Set(snippets)].slice(0, 8),
  };
}

export function buildTopicReport(
  profile: TopicProfile,
  jobId: string,
  pages: PageRecord[],
  pagesCrawled: number,
  minRelevance = 0.12,
): TopicReport {
  const intelPages: TopicPageIntel[] = [];
  const seen = new Set<string>();
  const allSocial: string[] = [];
  const allSnippets: string[] = [];
  const relatedUrls: string[] = [];

  for (const page of pages) {
    if (seen.has(page.url)) continue;
    seen.add(page.url);
    let body = "";
    if (page.contentPath) {
      try {
        body = readFileSync(page.contentPath, "utf8");
      } catch {
        /* skip */
      }
    }
    const relevance =
      (page.metadata?.topicRelevance as number | undefined) ??
      scorePage(page.url, page.title, body, profile);
    if (relevance < minRelevance) continue;
    const intel = extractPageIntel(page.url, body, profile, relevance);
    intelPages.push(intel);
    allSocial.push(...intel.socialLinks.filter(isValidSocialLink));
    allSnippets.push(...intel.snippets);
    relatedUrls.push(page.url);
  }
  intelPages.sort((a, b) => b.relevance - a.relevance);
  return {
    topic: profile.raw,
    jobId,
    pagesCrawled,
    relevantPages: intelPages.length,
    pages: intelPages,
    aggregatedSocialLinks: [...new Set(allSocial)],
    aggregatedLocations: [],
    aggregatedSnippets: [...new Set(allSnippets)].slice(0, 20),
    relatedUrls: [...new Set(relatedUrls)],
  };
}

export function formatReportText(report: TopicReport): string {
  const lines = [
    `Topic: ${report.topic}`,
    `Job: ${report.jobId}`,
    `Pages crawled: ${report.pagesCrawled} | Relevant: ${report.relevantPages}`,
    "",
  ];
  if (report.aggregatedSocialLinks.length) {
    lines.push("Social / profile links");
    for (const l of report.aggregatedSocialLinks.slice(0, 15)) lines.push(`  - ${l}`);
    lines.push("");
  }
  lines.push("Relevant pages");
  for (const p of report.pages.slice(0, 15)) {
    lines.push(`\n[${p.relevance.toFixed(2)}] ${p.url}`);
    if (p.title) lines.push(`  Title: ${p.title.slice(0, 140)}`);
    if (p.githubName) lines.push(`  GitHub name: ${p.githubName}`);
    if (p.githubBio) lines.push(`  GitHub bio: ${p.githubBio.slice(0, 160)}`);
    for (const item of p.profileItems.slice(0, 5)) lines.push(`  - ${item.slice(0, 120)}`);
    for (const s of p.snippets.slice(0, 2)) lines.push(`  > ${s.slice(0, 200)}`);
  }
  return lines.join("\n");
}

export function saveReport(report: TopicReport, path: string): void {
  mkdirSync(path.replace(/[/\\][^/\\]+$/, ""), { recursive: true });
  writeFileSync(path, JSON.stringify(report, null, 2), "utf8");
}

export async function runTopicLookup(
  config: import("../core/config.js").AppConfig,
  security: import("../security/nomad.js").NomadSecurityStack | null,
  opts: {
    topic: string;
    extraSeeds?: string[];
    maxDepth?: number;
    maxPages?: number;
    minRelevance?: number;
    minLinkScore?: number;
    followWaves?: number;
    jsRendering?: boolean;
  },
): Promise<TopicReport> {
  const { Orchestrator } = await import("../core/orchestrator.js");
  const profile = TopicProfile.parse(opts.topic);
  const orchestrator = new Orchestrator(config, security);
  orchestrator.init();

  try {
    let seeds = buildTopicSeeds(profile, opts.extraSeeds ?? []);
    const enriched = await enrichSeedsFromGithubSearch(profile, {
      userAgent: config.orchestrator.userAgent,
      timeoutMs: config.orchestrator.requestTimeoutSeconds * 1000,
    });
    seeds = [...new Set([...seeds, ...enriched])];
    if (security) {
      const blocked = new Set(security.ssrfGuard.validateMany(seeds).map((b) => b[0]));
      seeds = seeds.filter((s) => !blocked.has(s));
    }

    const spec = {
      seeds: seeds.slice(0, 20),
      engine: "auto" as const,
      maxDepth: opts.maxDepth ?? 2,
      maxPages: opts.maxPages ?? 40,
      includeArchive: false,
      includeSitemaps: false,
      jsRendering: opts.jsRendering ?? false,
      topic: profile.raw,
      topicMinLinkScore: opts.minLinkScore ?? 0.1,
      topicMinRelevance: opts.minRelevance ?? 0.12,
      topicFollowRelated: true,
    };

    let job = await orchestrator.submitJob(spec);
    while (job.status === "running" || job.status === "pending") {
      await sleep(500);
      job = (await orchestrator.getJob(job.id))!;
    }

    let pages = orchestrator.listPages(job.id, 5000);

    if ((opts.followWaves ?? 2) > 1) {
      const report1 = buildTopicReport(profile, job.id, pages, job.pagesCrawled, opts.minRelevance);
      const waveSeeds = report1.aggregatedSocialLinks
        .filter((u) => /github\.com|x\.com|twitter\.com/.test(u))
        .slice(0, 10);
      if (waveSeeds.length) {
        const waveJob = await orchestrator.submitJob({
          ...spec,
          seeds: waveSeeds,
          maxDepth: 1,
          maxPages: Math.min(20, opts.maxPages ?? 40),
        });
        let w = waveJob;
        while (w.status === "running" || w.status === "pending") {
          await sleep(500);
          w = (await orchestrator.getJob(w.id))!;
        }
        pages = [...pages, ...orchestrator.listPages(w.id, 5000)];
        return buildTopicReport(
          profile,
          job.id,
          pages,
          job.pagesCrawled + w.pagesCrawled,
          opts.minRelevance,
        );
      }
    }

    return buildTopicReport(profile, job.id, pages, job.pagesCrawled, opts.minRelevance);
  } finally {
    orchestrator.shutdown();
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
