export type EngineType =
  | "http"
  | "playwright"
  | "mechanical"
  | "archive"
  | "katana"
  | "splash"
  | "scrapy"
  | "auto";

export type PageSource = "live" | "wayback" | "common_crawl" | "sitemap" | "seed";

export type CrawlStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

export type Role = "viewer" | "operator" | "admin" | "sovereign";

export interface CrawlJobSpec {
  seeds: string[];
  engine?: EngineType;
  maxDepth?: number;
  maxPages?: number;
  includeArchive?: boolean;
  includeSitemaps?: boolean;
  jsRendering?: boolean;
  allowedDomains?: string[] | null;
  metadata?: Record<string, unknown>;
  topic?: string | null;
  topicMinLinkScore?: number;
  topicMinRelevance?: number;
  topicFollowRelated?: boolean;
}

export interface CrawlJob extends CrawlJobSpec {
  id: string;
  status: CrawlStatus;
  createdAt: string;
  startedAt?: string | null;
  finishedAt?: string | null;
  pagesCrawled: number;
  pagesFailed: number;
  error?: string | null;
}

export interface PageRecord {
  url: string;
  finalUrl?: string | null;
  statusCode?: number | null;
  contentType?: string | null;
  title?: string | null;
  depth: number;
  source: PageSource;
  engine: EngineType;
  fetchedAt: string;
  contentPath?: string | null;
  contentHash?: string | null;
  linksFound: number;
  archiveTimestamp?: string | null;
  metadata: Record<string, unknown>;
}

export interface FetchResult {
  url: string;
  finalUrl: string;
  statusCode: number;
  headers: Record<string, string>;
  body: Buffer;
  contentType?: string | null;
  engine: EngineType;
  source: PageSource;
  archiveTimestamp?: string | null;
  error?: string | null;
}

export function fetchOk(result: FetchResult): boolean {
  return result.statusCode >= 200 && result.statusCode < 400 && !result.error;
}

export interface FrontierEntry {
  url: string;
  depth: number;
  source: PageSource;
  priority: number;
  archiveTimestamp?: string | null;
}

export interface Principal {
  subject: string;
  roles: Role[];
}

export interface TopicPageIntel {
  url: string;
  title?: string | null;
  relevance: number;
  metaDescription?: string | null;
  headings: string[];
  socialLinks: string[];
  locations: string[];
  emails: string[];
  githubName?: string | null;
  githubBio?: string | null;
  profileItems: string[];
  snippets: string[];
}

export interface TopicReport {
  topic: string;
  jobId: string;
  pagesCrawled: number;
  relevantPages: number;
  pages: TopicPageIntel[];
  aggregatedSocialLinks: string[];
  aggregatedLocations: string[];
  aggregatedSnippets: string[];
  relatedUrls: string[];
}
