import type { ChatDocument } from "../chat/algorithm-chatbot.js";
import {
  isCorpusStale,
  loadScribdCorpus,
  scribdDocumentsToChatDocuments,
  type ScribdCorpus,
} from "./scribd-corpus.js";
import { scribdConfigFromEnv, syncScribdLibrary, type ScribdConfig } from "./scribd.js";

export interface ScribdLoadOptions {
  forceSync?: boolean;
  config?: ScribdConfig;
  syncTtlHours?: number;
}

export interface ScribdLoadResult {
  corpus: ScribdCorpus;
  documents: ChatDocument[];
  synced: boolean;
}

export async function loadScribdKnowledge(opts: ScribdLoadOptions = {}): Promise<ScribdLoadResult> {
  const config = opts.config ?? scribdConfigFromEnv();
  const ttl = opts.syncTtlHours ?? Number(process.env.SCRIBD_SYNC_TTL_HOURS ?? 24);
  let corpus = loadScribdCorpus(config.corpusPath);
  let synced = false;

  if (!corpus || opts.forceSync || isCorpusStale(corpus, ttl)) {
    corpus = await syncScribdLibrary(config);
    synced = true;
  }

  return {
    corpus,
    documents: scribdDocumentsToChatDocuments(corpus.documents),
    synced,
  };
}

export function isScribdDomain(domain?: string): boolean {
  return domain?.trim().toLowerCase() === "scribd";
}
