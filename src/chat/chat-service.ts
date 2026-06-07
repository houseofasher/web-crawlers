import { randomUUID } from "node:crypto";
import type { AppConfig } from "../core/config.js";
import { allowedDomainsFromSeeds, resolveDomainSeeds } from "../core/domain-seeds.js";
import type { Orchestrator } from "../core/orchestrator.js";
import {
  createSession,
  respondAlgorithm,
  type ChatDocument,
  type ChatReply,
  type ChatSession,
} from "./algorithm-chatbot.js";
import { prioritizeSeedsForQuestion } from "./retrieval-ranker.js";
import { assertLiveSeeds, pagesToLiveDocuments } from "./live-data-policy.js";
import { isScribdDomain, loadScribdKnowledge } from "../sources/scribd-service.js";

const sessions = new Map<string, ChatSession>();

export interface ChatRequest {
  message: string;
  sessionId?: string;
  domain?: string;
  seeds?: string[];
  maxDepth?: number;
  maxPages?: number;
  timeoutMs?: number;
  /** Merge synced Scribd library corpus into retrieval. */
  includeScribd?: boolean;
  forceScribdSync?: boolean;
}

export interface ChatResponse extends ChatReply {
  sessionId: string;
  crawled: boolean;
  jobId?: string;
  livePageCount: number;
  scribdDocumentCount?: number;
  scribdSynced?: boolean;
}

function getOrCreateSession(sessionId?: string): ChatSession {
  if (sessionId && sessions.has(sessionId)) {
    return sessions.get(sessionId)!;
  }
  const session = createSession(sessionId ?? randomUUID());
  sessions.set(session.id, session);
  return session;
}

function resolveLiveSeeds(req: ChatRequest): string[] {
  const seeds =
    req.seeds?.filter(Boolean) ??
    (req.domain?.trim() ? resolveDomainSeeds(req.domain) : []);
  return assertLiveSeeds(seeds);
}

async function crawlLiveDocuments(
  orchestrator: Orchestrator,
  req: ChatRequest,
): Promise<{ documents: ChatDocument[]; jobId?: string; seeds: string[] }> {
  const topic = req.message.trim();
  const seeds = prioritizeSeedsForQuestion(resolveLiveSeeds(req), topic);

  const timeoutMs = req.timeoutMs ?? 120_000;
  const pollMs = 1500;
  const job = await orchestrator.submitJob({
    seeds,
    maxDepth: req.maxDepth ?? 2,
    maxPages: req.maxPages ?? 15,
    includeArchive: false,
    includeSitemaps: false,
    jsRendering: false,
    topic,
    topicFollowRelated: false,
    allowedDomains: allowedDomainsFromSeeds(seeds),
  });

  const finished = await orchestrator.waitForJob(job.id, { timeoutMs, pollMs });
  if (!finished || finished.status !== "completed") {
    throw new Error(`CRAWL_INCOMPLETE:${finished?.status ?? "unknown"}`);
  }

  const pages = orchestrator.listPagesWithText(job.id, req.maxPages ?? 15, 0);
  const allowed = allowedDomainsFromSeeds(seeds);
  const documents = pagesToLiveDocuments(pages, allowed);
  if (!documents.length) {
    throw new Error("LIVE_DATA_REQUIRED — crawl completed but no live web pages were retrieved");
  }

  return { documents, jobId: job.id, seeds };
}

async function resolveChatDocuments(
  orchestrator: Orchestrator,
  req: ChatRequest,
): Promise<{
  documents: ChatDocument[];
  seeds: string[];
  jobId?: string;
  scribdDocumentCount: number;
  scribdSynced: boolean;
  crawled: boolean;
}> {
  const useScribdOnly = isScribdDomain(req.domain);
  const mergeScribd = useScribdOnly || req.includeScribd === true;

  let scribdDocs: ChatDocument[] = [];
  let scribdSynced = false;
  if (mergeScribd) {
    const scribd = await loadScribdKnowledge({ forceSync: req.forceScribdSync });
    scribdDocs = scribd.documents;
    scribdSynced = scribd.synced;
  }

  if (useScribdOnly) {
    if (!scribdDocs.length) {
      throw new Error("SCRIBD_EMPTY — sync your library first: omnispider scribd sync");
    }
    return {
      documents: scribdDocs,
      seeds: [resolveDomainSeeds("scribd")[0] ?? "https://www.scribd.com/home"],
      scribdDocumentCount: scribdDocs.length,
      scribdSynced,
      crawled: false,
    };
  }

  const crawled = await crawlLiveDocuments(orchestrator, req);
  const documents = [...scribdDocs, ...crawled.documents];
  if (!documents.length) {
    throw new Error("LIVE_DATA_REQUIRED — no documents from crawl or Scribd corpus");
  }

  return {
    documents,
    seeds: crawled.seeds,
    jobId: crawled.jobId,
    scribdDocumentCount: scribdDocs.length,
    scribdSynced,
    crawled: true,
  };
}

export async function handleChat(
  _config: AppConfig,
  orchestrator: Orchestrator,
  req: ChatRequest,
): Promise<ChatResponse> {
  const message = req.message.trim();
  if (!message) throw new Error("message required");

  const session = getOrCreateSession(req.sessionId);
  const resolved = await resolveChatDocuments(orchestrator, req);

  const reply = respondAlgorithm(session, message, resolved.documents, resolved.seeds);
  sessions.set(reply.session.id, reply.session);

  return {
    ...reply,
    sessionId: reply.session.id,
    crawled: resolved.crawled,
    jobId: resolved.jobId,
    livePageCount: resolved.documents.length,
    scribdDocumentCount: resolved.scribdDocumentCount,
    scribdSynced: resolved.scribdSynced,
  };
}

/** Test helper — clear in-memory sessions. */
export function resetChatSessions(): void {
  sessions.clear();
}
