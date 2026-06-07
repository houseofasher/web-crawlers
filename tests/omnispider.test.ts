import { describe, it, expect } from "vitest";
import { TopicProfile, scoreText, scoreLink, scorePage } from "../src/topic/index.js";
import { SSRFGuard } from "../src/security/nomad.js";
import { normalizeUrl } from "../src/core/policy.js";

describe("topic", () => {
  it("parses terms", () => {
    const p = TopicProfile.parse("Asher Shepherd Newton Cape Coral Florida");
    expect(p.terms).toContain("asher");
    expect(p.terms).toContain("newton");
  });

  it("scores github profile", () => {
    const p = TopicProfile.parse("Asher Newton");
    expect(scoreLink("https://github.com/shep95", "Asher Newton", p)).toBeGreaterThan(0.2);
  });
});

describe("security", () => {
  it("blocks localhost", () => {
    const g = new SSRFGuard({});
    expect(g.validateUrl("http://127.0.0.1/admin").ok).toBe(false);
  });
});

describe("policy", () => {
  it("normalizes urls", () => {
    expect(normalizeUrl("https://Example.com/path/")).toBe("https://example.com/path");
  });
});
