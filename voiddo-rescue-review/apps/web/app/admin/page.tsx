import { fetchJson } from "../lib/api";
import { headers } from "next/headers";

const labels: Record<string, string> = {
  leads_total: "leads total",
  qualified_leads: "qualified",
  audit_pages_generated: "audit pages",
  payments: "payments",
  subscriptions: "subscriptions",
  customers: "customers",
  fix_requests: "fix requests",
  human_review_required: "human review",
};

export default async function AdminPage() {
  const requestHeaders = await headers();
  const authorization = requestHeaders.get("authorization") || "";
  const data = await fetchJson("/admin/metrics", authorization ? { Authorization: authorization } : {});
  const metrics = data || {};
  const cards = Object.entries(labels).map(([key, label]) => [String(metrics[key] ?? 0), label]);
  const scans = metrics.scans || {};
  const emails = metrics.emails || {};
  const switches = metrics.kill_switches || {};
  const ops = [
    ["scouts", metrics.scout_runs ?? 0],
    ["campaigns", metrics.campaigns ?? 0],
    ["agents", metrics.agent_runs ?? 0],
    ["onboarding", metrics.onboarding_tasks ?? 0],
  ];
  const selfOps = [
    ["economics", metrics.economics_snapshots ?? 0],
    ["self audits", metrics.self_audit_runs ?? 0],
    ["fix queue", metrics.self_fix_tasks_open ?? 0],
    ["learning", metrics.self_learning_events ?? 0],
    ["build queue", metrics.self_build_queue_open ?? 0],
    ["mailer decisions", metrics.autonomous_mailer_decisions ?? 0],
    ["mailer drafts", metrics.mailer_drafts ?? 0],
    ["plugin gates", metrics.quality_plugin_runs ?? 0],
    ["simulations", metrics.revenue_simulation_runs ?? 0],
    ["clean windows", metrics.mail_clean_window_checks ?? 0],
    ["scout checks", metrics.scout_self_checks ?? 0],
    ["audit strength", metrics.audit_strength_scores ?? 0],
    ["language gates", metrics.public_language_gate_runs ?? 0],
  ];

  return (
    <div className="shell">
      <header className="nav"><div className="brand"><span className="mark">vø</span> Rescue Admin</div><nav className="navlinks"><a href="/">Product</a><a href="/status">Status</a></nav></header>
      <main id="main" className="dashboard">
        <aside className="sidebar">
          <div className="eyebrow">Control room</div>
          <div className="actions tight">
            <a className="button primary" href="/admin">Open pipeline</a>
            <a className="button secondary" href="/r/demo">View audit</a>
          </div>
          <h1 style={{fontSize: 34, lineHeight: 1.05}}>Pipeline is gated</h1>
          <p className="lede" style={{fontSize: 15}}>Live sends, warmup, auto-replies, and Paddle customer-facing provisioning stay paused until P0 gates pass.</p>
        </aside>
        <section className="content">
          <div className="metric-grid">
            {cards.map(([value, label]) => <div className="metric" key={label}><strong>{value}</strong><span>{label}</span></div>)}
          </div>
          <div className="panel">
            <h2>Scanner Jobs</h2>
            {["queued", "running", "completed", "failed"].map((item) => (
              <div className="row" key={item}><span className="tag">{item}</span><span>scan jobs</span><span className="score">{scans[item] ?? 0}</span></div>
            ))}
          </div>
          <div className="panel">
            <h2>Outreach Queue</h2>
            {["queued", "sent", "bounced", "replied"].map((item) => (
              <div className="row" key={item}><span className="tag">{item}</span><span>messages</span><span className="score">{emails[item] ?? 0}</span></div>
            ))}
          </div>
          <div className="panel">
            <h2>Kill Switches</h2>
            {Object.entries(switches).map(([key, value]) => (
              <div className="row" key={key}><span className="tag">{value ? "on" : "off"}</span><span>{key.replaceAll("_", " ")}</span><span className="score">{value ? "blocked" : "armed"}</span></div>
            ))}
          </div>
          <div className="panel">
            <h2>Owner Commands</h2>
            <div className="row"><span className="tag">stored</span><span>gated inbox commands</span><span className="score">{metrics.owner_commands ?? 0}</span></div>
            <div className="row"><span className="tag">visual</span><span>QA runs</span><span className="score">{metrics.visual_qa_runs ?? 0}</span></div>
            <div className="row"><span className="tag">mail</span><span>QA runs</span><span className="score">{metrics.mail_qa_runs ?? 0}</span></div>
          </div>
          <div className="panel">
            <h2>Autonomous Agents</h2>
            {ops.map(([label, value]) => (
              <div className="row" key={String(label)}><span className="tag">agent</span><span>{String(label)}</span><span className="score">{String(value)}</span></div>
            ))}
          </div>
          <div className="panel">
            <h2>Self-Operating Engine</h2>
            {selfOps.map(([label, value]) => (
              <div className="row" key={String(label)}><span className="tag">self</span><span>{String(label)}</span><span className="score">{String(value)}</span></div>
            ))}
          </div>
          <div className="panel">
            <h2>Launch Pools</h2>
            <div className="row"><span className="tag">warmup</span><span>approved recipient pool</span><span className="score">{metrics.warmup_recipients ?? 0}</span></div>
            <div className="row"><span className="tag">test</span><span>approved deliverability inboxes</span><span className="score">{metrics.test_inboxes ?? 0}</span></div>
            <div className="row"><span className="tag">preview</span><span>outreach preview batches</span><span className="score">{metrics.outreach_preview_batches ?? 0}</span></div>
          </div>
        </section>
      </main>
    </div>
  );
}
