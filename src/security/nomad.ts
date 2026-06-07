import { createHmac, randomBytes, createHash } from "node:crypto";
import { appendFileSync, existsSync, mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import type { AppConfig, SecurityConfig } from "../core/config.js";
import type { Role } from "../core/models.js";
import { safeEqual } from "../core/policy.js";

export type AuditEventType =
  | "job_started"
  | "job_completed"
  | "job_failed"
  | "api_request"
  | "api_denied"
  | "rate_limit_exceeded"
  | "replay_detected"
  | "client_rejected_allowlist"
  | "ssrf_blocked"
  | "organism_lockdown"
  | "audit_chain_breach";

export interface AuditEvent {
  id: string;
  ts: string;
  type: AuditEventType;
  correlationId?: string;
  peer?: string;
  detail?: string;
  prevEntryId: string;
  entryMac: string;
}

export class AuditLog {
  private chainKey: Buffer;
  private entries: AuditEvent[] = [];
  private filePath: string | null = null;

  constructor(logDir: string | null, chainKeyHex?: string) {
    this.chainKey = chainKeyHex
      ? Buffer.from(chainKeyHex, "hex")
      : randomBytes(32);
    if (logDir) {
      mkdirSync(logDir, { recursive: true });
      this.filePath = join(logDir, "omnispider-audit.jsonl");
      this.loadFromDisk();
    }
  }

  private signEntry(event: Omit<AuditEvent, "entryMac">): string {
    const prevId = event.prevEntryId || "GENESIS";
    const payload = `${event.id}|${event.ts}|${event.type}|${prevId}|${event.detail ?? ""}`;
    return createHmac("sha256", this.chainKey).update(payload).digest("hex");
  }

  private loadFromDisk(): void {
    if (!this.filePath || !existsSync(this.filePath)) return;
    for (const line of readFileSync(this.filePath, "utf8").split("\n")) {
      if (!line.trim()) continue;
      try {
        this.entries.push(JSON.parse(line) as AuditEvent);
      } catch {
        /* skip */
      }
    }
  }

  record(
    type: AuditEventType,
    fields: { correlationId?: string; peer?: string; detail?: string } = {},
  ): AuditEvent {
    const prev = this.entries[this.entries.length - 1];
    const base: Omit<AuditEvent, "entryMac"> = {
      id: `${Date.now()}-${randomBytes(4).toString("hex")}`,
      ts: new Date().toISOString(),
      type,
      correlationId: fields.correlationId,
      peer: fields.peer,
      detail: fields.detail,
      prevEntryId: prev?.id ?? "",
    };
    const event: AuditEvent = { ...base, entryMac: this.signEntry(base) };
    this.entries.push(event);
    if (this.filePath) appendFileSync(this.filePath, JSON.stringify(event) + "\n");
    return event;
  }

  verifyChain(): { valid: boolean; errors: string[] } {
    const errors: string[] = [];
    let prevId = "";
    for (const entry of this.entries) {
      const { entryMac, ...base } = entry;
      if (entryMac !== this.signEntry(base)) errors.push(`Entry ${entry.id}: HMAC mismatch`);
      if (entry.prevEntryId !== prevId) errors.push(`Entry ${entry.id}: chain broken`);
      prevId = entry.id;
    }
    return { valid: errors.length === 0, errors };
  }

  query(limit = 100): AuditEvent[] {
    return this.entries.slice(-limit);
  }

  fingerprint(): string {
    return this.chainKey.subarray(0, 8).toString("hex");
  }
}

const ROLE_RANK: Record<Role, number> = {
  viewer: 1,
  operator: 2,
  admin: 3,
  sovereign: 4,
};

export class RbacPolicy {
  private routeRoles = new Map<string, Role>([
    ["GET /health", "viewer"],
    ["GET /organism/vitals", "viewer"],
    ["GET /v1/engines", "viewer"],
    ["GET /v1/jobs", "operator"],
    ["GET /v1/jobs/:id", "operator"],
    ["GET /v1/jobs/:id/pages", "operator"],
    ["POST /v1/jobs", "operator"],
    ["POST /v1/lookup", "operator"],
    ["GET /v1/audit", "admin"],
  ]);

  authorize(principal: { roles: Role[] } | null, method: string, path: string): boolean {
    const required = this.matchRoute(method, path);
    if (!principal) return false;
    const need = ROLE_RANK[required];
    return principal.roles.some((r) => ROLE_RANK[r] >= need);
  }

  private matchRoute(method: string, path: string): Role {
    const key = `${method.toUpperCase()} ${path}`;
    if (this.routeRoles.has(key)) return this.routeRoles.get(key)!;
    for (const [pattern, role] of this.routeRoles) {
      const [, patternPath] = pattern.split(" ");
      if (patternPath.includes(":id") && path.startsWith(patternPath.replace(":id", "").replace(/\/$/, ""))) {
        return role;
      }
    }
    return "admin";
  }
}

export class ApiKeyRegistry {
  private keys = new Map<string, { subject: string; roles: Role[] }>();
  readonly requireAuth: boolean;

  constructor(config: SecurityConfig) {
    this.requireAuth = config.requireAuth && config.apiKeys.length > 0;
    for (const entry of config.apiKeys) {
      const [hash, roleName] = entry.split(":", 2);
      if (!hash || !roleName) continue;
      this.keys.set(hash.trim(), {
        subject: `key:${roleName}`,
        roles: [roleName.trim().toLowerCase() as Role],
      });
    }
  }

  static hashKey(raw: string): string {
    return createHash("sha256").update(raw).digest("hex");
  }

  verifyToken(token: string): { subject: string; roles: Role[] } | null {
    const hash = ApiKeyRegistry.hashKey(token);
    for (const [keyHash, principal] of this.keys) {
      if (safeEqual(keyHash, hash)) return principal;
    }
    return null;
  }

  static generateKey(role: Role = "operator"): { raw: string; configEntry: string } {
    const raw = randomBytes(24).toString("base64url");
    return { raw, configEntry: `${ApiKeyRegistry.hashKey(raw)}:${role}` };
  }
}

export class RateLimiter {
  private maxRpm: number;
  private maxConnections: number;
  private active = 0;
  private timestamps: number[] = [];

  constructor(maxConnections: number, maxRpm: number) {
    this.maxConnections = maxConnections;
    this.maxRpm = maxRpm;
  }

  tryAcquire(): boolean {
    const now = Date.now();
    this.timestamps = this.timestamps.filter((t) => t >= now - 60000);
    if (this.timestamps.length >= this.maxRpm || this.active >= this.maxConnections) return false;
    this.active++;
    this.timestamps.push(now);
    return true;
  }

  release(): void {
    this.active = Math.max(0, this.active - 1);
  }
}

export class DistributedRateLimiter {
  private max: number;
  private buckets = new Map<string, number[]>();

  constructor(maxPerMinute: number) {
    this.max = maxPerMinute;
  }

  tryAcquire(clientId: string): boolean {
    const now = Date.now();
    const hits = (this.buckets.get(clientId) ?? []).filter((t) => t >= now - 60000);
    if (hits.length >= this.max) return false;
    hits.push(now);
    this.buckets.set(clientId, hits);
    return true;
  }
}

export class ReplayGuard {
  private seen = new Map<string, number>();
  constructor(
    private maxClockSkewMs = 60000,
    private nonceTtlMs = 120000,
    private maxEntries = 10000,
  ) {}

  validate(nonce: string, timestampMs: number, correlationId: string): void {
    this.purge();
    const now = Date.now();
    if (timestampMs <= 0 || Math.abs(now - timestampMs) > this.maxClockSkewMs) {
      throw new Error("Message timestamp outside allowed clock skew window.");
    }
    const key = `${correlationId}:${nonce}`;
    if (this.seen.has(key)) throw new Error("Replay detected: duplicate nonce.");
    this.seen.set(key, now + this.nonceTtlMs);
    if (this.seen.size > this.maxEntries) {
      const first = this.seen.keys().next().value;
      if (first) this.seen.delete(first);
    }
  }

  private purge(): void {
    const now = Date.now();
    for (const [k, exp] of this.seen) if (exp <= now) this.seen.delete(k);
  }
}

export class SSRFGuard {
  private blockPrivate: boolean;
  private blockLinkLocal: boolean;
  private allowedSchemes: string[];

  constructor(opts: { blockPrivateIps?: boolean; blockLinkLocal?: boolean; allowedSchemes?: string[] } = {}) {
    this.blockPrivate = opts.blockPrivateIps ?? true;
    this.blockLinkLocal = opts.blockLinkLocal ?? true;
    this.allowedSchemes = opts.allowedSchemes ?? ["http", "https"];
  }

  validateUrl(url: string): { ok: boolean; reason?: string } {
    let parsed: URL;
    try {
      parsed = new URL(url.trim());
    } catch {
      return { ok: false, reason: "invalid_url" };
    }
    const scheme = parsed.protocol.replace(":", "");
    if (!this.allowedSchemes.includes(scheme)) return { ok: false, reason: "scheme_not_allowed" };
    const host = parsed.hostname.toLowerCase();
    if (["localhost", "127.0.0.1", "::1", "0.0.0.0"].includes(host)) {
      return { ok: false, reason: "blocked_host" };
    }
    if (host.endsWith(".local") || host.endsWith(".internal")) {
      return { ok: false, reason: "blocked_tld" };
    }
    // Literal IP checks
    if (/^\d+\.\d+\.\d+\.\d+$/.test(host)) {
      const parts = host.split(".").map(Number);
      if (parts[0] === 10) return { ok: false, reason: "private_ip" };
      if (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31) return { ok: false, reason: "private_ip" };
      if (parts[0] === 192 && parts[1] === 168) return { ok: false, reason: "private_ip" };
      if (parts[0] === 127) return { ok: false, reason: "loopback_ip" };
    }
    return { ok: true };
  }

  validateMany(urls: string[]): Array<[string, string]> {
    return urls
      .map((u) => {
        const r = this.validateUrl(u);
        return r.ok ? null : ([u, r.reason ?? "blocked"] as [string, string]);
      })
      .filter(Boolean) as Array<[string, string]>;
  }
}

export class VitalGuard {
  private audit: AuditLog;
  private devMode: boolean;
  private pulse = 1;
  private lockdownReason: string | null = null;

  constructor(audit: AuditLog, devMode = false) {
    this.audit = audit;
    this.devMode = devMode;
  }

  pulseCheck(): void {
    this.pulse++;
    if (this.devMode) {
      this.lockdownReason = null;
      return;
    }
    const { valid, errors } = this.audit.verifyChain();
    this.lockdownReason = valid ? null : errors[0] ?? "audit_chain_invalid";
  }

  isVital(): boolean {
    return this.devMode || this.lockdownReason === null;
  }

  requireVital(op: string): void {
    if (!this.isVital()) throw new Error(`ORGANISM_LOCKDOWN: ${op} blocked — ${this.lockdownReason}`);
  }

  getVitalsReport() {
    const { valid } = this.audit.verifyChain();
    return {
      vital: this.isVital(),
      pulseGeneration: this.pulse,
      organismFingerprint: this.audit.fingerprint(),
      lockdownReason: this.lockdownReason,
      doctrine: "All security organs must be vital simultaneously. Partial compromise = total shutdown.",
      organs: [
        { id: "audit_immune", name: "Audit Immune System", state: valid ? "vital" : "critical" },
        { id: "gateway_skin", name: "Gateway Skin", state: this.isVital() ? "vital" : "critical" },
        { id: "ssrf_lungs", name: "SSRF Lungs", state: "vital" },
      ],
    };
  }
}

export class ClientAllowlist {
  private allowed: Set<string>;
  private require: boolean;

  constructor(config: SecurityConfig) {
    this.allowed = new Set(config.clientAllowlist.map((s) => s.trim()).filter(Boolean));
    this.require = config.requireClientAllowlist;
  }

  isAllowed(clientId: string): boolean {
    if (this.require && this.allowed.size === 0) return false;
    if (this.allowed.size === 0) return true;
    return this.allowed.has(clientId);
  }
}

export interface NomadSecurityStack {
  audit: AuditLog;
  rbac: RbacPolicy;
  auth: ApiKeyRegistry;
  allowlist: ClientAllowlist;
  rateLimiter: RateLimiter;
  distributed: DistributedRateLimiter;
  replayGuard: ReplayGuard;
  vitalGuard: VitalGuard;
  ssrfGuard: SSRFGuard;
}

export function buildSecurityStack(config: AppConfig): NomadSecurityStack {
  const audit = new AuditLog(
    config.security.auditLogDir,
    config.security.auditChainKey || undefined,
  );
  const vitalGuard = new VitalGuard(audit, config.security.devMode);
  vitalGuard.pulseCheck();
  return {
    audit,
    rbac: new RbacPolicy(),
    auth: new ApiKeyRegistry(config.security),
    allowlist: new ClientAllowlist(config.security),
    rateLimiter: new RateLimiter(
      config.security.maxConnections,
      config.security.maxRequestsPerMinute,
    ),
    distributed: new DistributedRateLimiter(config.security.maxRequestsPerClientPerMinute),
    replayGuard: new ReplayGuard(
      config.security.replayMaxClockSkewMs,
      config.security.replayNonceTtlMs,
    ),
    vitalGuard,
    ssrfGuard: new SSRFGuard({
      blockPrivateIps: config.security.blockPrivateIps,
      blockLinkLocal: config.security.blockLinkLocal,
      allowedSchemes: config.policy.allowedSchemes,
    }),
  };
}
