#!/usr/bin/env node
import { Command } from "commander";
import { resolve } from "node:path";
import { loadConfig } from "./core/config.js";
import { Orchestrator } from "./core/orchestrator.js";
import { buildSecurityStack, ApiKeyRegistry } from "./security/nomad.js";
import {
  formatReportText,
  runTopicLookup,
  saveReport,
} from "./topic/index.js";
import { ArchiveEngine } from "./engines/registry.js";
import { startApi } from "./api.js";

const program = new Command();

program
  .name("omnispider")
  .description("Omnispider — all-in-one web spider orchestrator (TypeScript)")
  .version("1.0.0");

program
  .command("crawl")
  .description("Start a crawl job")
  .argument("<seeds...>", "Seed URLs")
  .option("-d, --depth <n>", "Max depth", "3")
  .option("-m, --max-pages <n>", "Max pages", "500")
  .option("--no-archive", "Skip Wayback Machine")
  .option("--no-sitemap", "Skip sitemap discovery")
  .option("--js", "Force JS rendering")
  .option("-c, --config <path>", "Config YAML path")
  .action(async (seeds: string[], opts) => {
    const config = loadConfig(opts.config);
    const security = config.security.enabled ? buildSecurityStack(config) : null;
    const orchestrator = new Orchestrator(config, security);
    orchestrator.init();
    try {
      const job = await orchestrator.submitJob({
        seeds,
        maxDepth: Number(opts.depth),
        maxPages: Number(opts.maxPages),
        includeArchive: opts.archive !== false,
        includeSitemaps: opts.sitemap !== false,
        jsRendering: !!opts.js,
      });
      console.log(`Job ${job.id} started — seeds: ${seeds.join(", ")}`);
      while (true) {
        const current = orchestrator.getJob(job.id);
        if (current && ["completed", "failed", "cancelled"].includes(current.status)) {
          console.log(
            `Job ${job.id} ${current.status}: ${current.pagesCrawled} pages, ${current.pagesFailed} failed`,
          );
          if (current.error) console.log(`Error: ${current.error}`);
          break;
        }
        await sleep(1000);
      }
    } finally {
      orchestrator.shutdown();
    }
  });

program
  .command("lookup")
  .description("Topic-centric lookup — find and follow pages about a person/topic")
  .argument("<topic>", "Topic query")
  .option("-s, --seed <url...>", "Extra seed URLs")
  .option("-d, --depth <n>", "Max depth", "2")
  .option("-m, --max-pages <n>", "Max pages", "40")
  .option("--min-relevance <n>", "Min relevance score", "0.12")
  .option("--waves <n>", "Follow-up profile waves", "2")
  .option("--json <path>", "Save JSON report")
  .option("-c, --config <path>", "Config path")
  .action(async (topic: string, opts) => {
    const config = loadConfig(opts.config);
    const security = config.security.enabled ? buildSecurityStack(config) : null;
    const report = await runTopicLookup(config, security, {
      topic,
      extraSeeds: opts.seed ?? [],
      maxDepth: Number(opts.depth),
      maxPages: Number(opts.maxPages),
      minRelevance: Number(opts.minRelevance),
      followWaves: Number(opts.waves),
    });
    console.log(formatReportText(report));
    if (opts.json) {
      saveReport(report, resolve(opts.json));
      console.log(`\nJSON report saved to ${opts.json}`);
    }
  });

program
  .command("archive")
  .description("List Wayback Machine snapshots for a URL")
  .argument("<url>", "URL to look up")
  .option("-c, --config <path>", "Config path")
  .action(async (url: string, opts) => {
    const config = loadConfig(opts.config);
    const archive = new ArchiveEngine(config);
    const snapshots = await archive.listSnapshots(url);
    if (!snapshots.length) {
      console.log("No snapshots found.");
      return;
    }
    for (const ts of snapshots) console.log(`${ts}  ${archive.waybackUrl(ts, url)}`);
  });

program
  .command("serve")
  .description("Start REST API server")
  .option("--host <host>", "Bind host")
  .option("--port <port>", "Bind port")
  .option("-c, --config <path>", "Config path")
  .action(async (opts) => {
    const config = loadConfig(opts.config);
    const host = opts.host ?? config.api.host;
    const port = Number(opts.port ?? config.api.port);
    await startApi(config, host, port);
  });

const security = program.command("security").description("Nomad Cyber security utilities");

security
  .command("generate-key")
  .option("-r, --role <role>", "viewer|operator|admin|sovereign", "operator")
  .action((opts) => {
    const { raw, configEntry } = ApiKeyRegistry.generateKey(opts.role);
    console.log(`API Key (save now — shown once):\n  ${raw}\n`);
    console.log(`Add to config/default.yaml under security.api_keys:\n  - "${configEntry}"`);
  });

security
  .command("vitals")
  .option("-c, --config <path>", "Config path")
  .action((opts) => {
    const config = loadConfig(opts.config);
    const stack = buildSecurityStack(config);
    const report = stack.vitalGuard.getVitalsReport();
    console.log(JSON.stringify(report, null, 2));
  });

program.parseAsync(process.argv).catch((err) => {
  console.error(err);
  process.exit(1);
});

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
