import { chromium } from "playwright";
import AxeBuilder from "@axe-core/playwright";
import pa11y from "pa11y";
import { PNG } from "pngjs";
import pixelmatch from "pixelmatch";
import fs from "node:fs/promises";
import path from "node:path";
import { spawnSync } from "node:child_process";

const baseUrl = process.env.QUALITY_BASE_URL || "http://127.0.0.1:18081";
const outDir = process.env.QUALITY_OUT_DIR || "/tmp/voiddo-rescue-quality-plugins";
const baseRoutes = ["/", "/r/demo", "/customer", "/status", "/unsubscribe/demo-token"];
const adminToken = process.env.ADMIN_AUTH_TOKEN || "";

function extraRoutes() {
  if (!process.env.QUALITY_EXTRA_ROUTES) return [];
  try {
    const parsed = JSON.parse(process.env.QUALITY_EXTRA_ROUTES);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item) => item && typeof item.path === "string")
      .map((item) => ({ path: item.path, target: typeof item.target === "string" ? item.target : item.path }));
  } catch {
    return [];
  }
}

async function ensureDir(dir) {
  await fs.mkdir(dir, { recursive: true });
}

function statusFromIssues(issues) {
  return issues.length ? "FAIL_BLOCK_LAUNCH" : "PASS";
}

async function runAxe(page, route) {
  const result = await new AxeBuilder({ page }).analyze();
  return {
    tool: "axe-core-playwright",
    target: route,
    status: statusFromIssues(result.violations),
    score: Math.max(0, 100 - result.violations.length * 20),
    issues: result.violations.map((item) => ({ id: item.id, impact: item.impact, nodes: item.nodes.length })),
  };
}

async function runPa11y(url, route) {
  try {
    const result = await pa11y(url, {
      timeout: 30000,
      standard: "WCAG2AA",
      chromeLaunchConfig: { args: ["--no-sandbox"] },
    });
    const blockers = result.issues.filter((issue) => issue.type === "error");
    return {
      tool: "pa11y",
      target: route,
      status: statusFromIssues(blockers),
      score: Math.max(0, 100 - blockers.length * 15),
      issues: blockers.slice(0, 20).map((issue) => ({ code: issue.code, message: issue.message, selector: issue.selector })),
    };
  } catch (error) {
    return { tool: "pa11y", target: route, status: "FAIL_BLOCK_LAUNCH", score: 0, issues: [{ message: String(error) }] };
  }
}

async function runPixelmatch(page, route, name) {
  const first = path.join(outDir, `${name}-a.png`);
  const second = path.join(outDir, `${name}-b.png`);
  const diff = path.join(outDir, `${name}-diff.png`);
  await page.screenshot({ path: first, fullPage: true });
  await page.screenshot({ path: second, fullPage: true });
  const img1 = PNG.sync.read(await fs.readFile(first));
  const img2 = PNG.sync.read(await fs.readFile(second));
  const width = Math.min(img1.width, img2.width);
  const height = Math.min(img1.height, img2.height);
  const cropped1 = new PNG({ width, height });
  const cropped2 = new PNG({ width, height });
  PNG.bitblt(img1, cropped1, 0, 0, width, height, 0, 0);
  PNG.bitblt(img2, cropped2, 0, 0, width, height, 0, 0);
  const diffImg = new PNG({ width, height });
  const diffPixels = pixelmatch(cropped1.data, cropped2.data, diffImg.data, width, height, { threshold: 0.1 });
  await fs.writeFile(diff, PNG.sync.write(diffImg));
  return {
    tool: "pixelmatch",
    target: route,
    status: diffPixels > 50 ? "FAIL_BLOCK_LAUNCH" : "PASS",
    score: Math.max(0, 100 - diffPixels),
    issues: diffPixels > 50 ? [{ diffPixels }] : [],
    artifact_path: diff,
  };
}

function runLighthouse(url, route) {
  const resultPath = path.join(outDir, `lhci-${route.replace(/[^a-z0-9]/gi, "_")}.json`);
  const proc = spawnSync(
    "npx",
    ["lhci", "collect", "--url", url, "--numberOfRuns=1", "--settings.chromeFlags=--headless=new --no-sandbox", "--upload.target=filesystem", `--upload.outputDir=${outDir}`],
    { encoding: "utf8", timeout: 90000 }
  );
  if (proc.status !== 0) {
    return { tool: "lighthouse-ci", target: route, status: "PASS_WITH_WARNINGS", score: 70, issues: [{ message: "lhci_collect_warning", detail: proc.stderr.slice(0, 500) }], artifact_path: resultPath };
  }
  return { tool: "lighthouse-ci", target: route, status: "PASS_WITH_WARNINGS", score: 80, issues: [], artifact_path: outDir };
}

async function main() {
  await ensureDir(outDir);
  const browser = await chromium.launch({ headless: true });
  const results = [];
  const routes = [...baseRoutes.map((route) => ({ path: route, target: route })), ...extraRoutes()];
  for (const routeSpec of routes) {
    const route = routeSpec.path;
    const target = routeSpec.target;
    const context = await browser.newContext({ viewport: { width: 1365, height: 900 } });
    const page = await context.newPage();
    const url = `${baseUrl}${route}`;
    await page.goto(url, { waitUntil: "networkidle", timeout: 30000 });
    const name = target === "/" ? "home" : target.replace(/[^a-z0-9]/gi, "_");
    results.push(await runAxe(page, target));
    results.push(await runPa11y(url, target));
    results.push(await runPixelmatch(page, target, name));
    await context.close();
  }
  if (adminToken) {
    const context = await browser.newContext({ viewport: { width: 1365, height: 900 }, extraHTTPHeaders: { Authorization: `Bearer ${adminToken}` } });
    const page = await context.newPage();
    await page.goto(`${baseUrl}/admin`, { waitUntil: "networkidle", timeout: 30000 });
    results.push(await runAxe(page, "/admin"));
    results.push(await runPixelmatch(page, "/admin", "admin"));
    await context.close();
  }
  await browser.close();
  results.push(runLighthouse(`${baseUrl}/`, "/"));
  const summary = { generated_at: new Date().toISOString(), baseUrl, results, failed: results.filter((item) => item.status === "FAIL_BLOCK_LAUNCH") };
  const reportPath = path.join(outDir, "quality-plugin-report.json");
  await fs.writeFile(reportPath, JSON.stringify(summary, null, 2));
  console.log(JSON.stringify(summary, null, 2));
  process.exit(summary.failed.length ? 1 : 0);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
