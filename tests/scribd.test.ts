import { describe, it, expect } from "vitest";
import {
  isCorpusStale,
  scribdDocumentsToChatDocuments,
  type ScribdCorpus,
} from "../src/sources/scribd-corpus.js";
import { isScribdDomain } from "../src/sources/scribd-service.js";

describe("scribd corpus", () => {
  it("detects scribd domain slug", () => {
    expect(isScribdDomain("scribd")).toBe(true);
    expect(isScribdDomain("computer_science")).toBe(false);
  });

  it("converts synced docs to live chat documents", () => {
    const docs = scribdDocumentsToChatDocuments([
      {
        id: "abc",
        title: "Introduction to Algorithms",
        url: "https://www.scribd.com/document/123/intro",
        text: "An algorithm is a finite sequence of rigorous instructions, typically used to solve a class of specific problems or to perform a computation.",
        syncedAt: "2026-06-07T12:00:00.000Z",
        source: "scribd_library",
      },
    ]);
    expect(docs).toHaveLength(1);
    expect(docs[0].source).toBe("live");
    expect(docs[0].url).toContain("scribd.com");
  });

  it("marks corpus stale after ttl", () => {
    const corpus: ScribdCorpus = {
      syncedAt: new Date(Date.now() - 48 * 3600_000).toISOString(),
      libraryUrl: "https://www.scribd.com/home",
      documents: [],
    };
    expect(isCorpusStale(corpus, 24)).toBe(true);
    expect(isCorpusStale(corpus, 0)).toBe(false);
  });
});
