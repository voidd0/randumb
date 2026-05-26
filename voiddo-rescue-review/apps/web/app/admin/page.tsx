import { fetchJson } from "../lib/api";

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
  const data = await fetchJson("/admin/metrics");
  const metrics = data || {};
  const cards = Object.entries(labels).map(([key, label]) => [String(metrics[key] ?? 0), label]);
  const scans = metrics.scans || {};
  const emails = metrics.emails || {};
  const switches = metrics.kill_switches || {};

  return (
    <div className="shell">
      <header className="nav"><div className="brand"><span className="mark">vø</span> Rescue Admin</div><nav className="navlinks"><a href="/">Product</a><a href="/status">Status</a></nav></header>
      <main id="main" className="dashboard">
        <aside className="sidebar">
          <div className="eyebrow">Control room</div>
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
        </section>
      </main>
    </div>
  );
}
