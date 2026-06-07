import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import type { ChatDocument } from "../chat/algorithm-chatbot.js";

export interface ScribdDocument {
  id: string;
  title: string;
  url: string;
  text: string;
  syncedAt: string;
  source: "scribd_library" | "scribd_pdf_import";
}

export interface ScribdCorpus {
  syncedAt: string;
  libraryUrl: string;
  documents: ScribdDocument[];
}

export function defaultCorpusPath(root = process.cwd()): string {
  return join(root, "data", "scribd", "corpus.json");
}

export function loadScribdCorpus(path = defaultCorpusPath()): ScribdCorpus | null {
  if (!existsSync(path)) return null;
  try {
    const parsed = JSON.parse(readFileSync(path, "utf8")) as ScribdCorpus;
    if (!parsed?.documents?.length) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function saveScribdCorpus(corpus: ScribdCorpus, path = defaultCorpusPath()): void {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, JSON.stringify(corpus, null, 2), "utf8");
}

export function scribdDocumentsToChatDocuments(docs: ScribdDocument[]): ChatDocument[] {
  return docs
    .filter((d) => d.text.length >= 80)
    .map((d) => ({
      text: d.text,
      url: d.url,
      title: d.title,
      source: "live" as const,
      fetchedAt: d.syncedAt,
    }));
}

export function isCorpusStale(corpus: ScribdCorpus, ttlHours: number): boolean {
  if (ttlHours <= 0) return false;
  const ageMs = Date.now() - new Date(corpus.syncedAt).getTime();
  return ageMs > ttlHours * 3600_000;
}
