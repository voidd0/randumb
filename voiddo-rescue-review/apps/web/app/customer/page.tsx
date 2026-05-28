import { fetchJson } from "../lib/api";

type Dashboard = {
  customer?: { status?: string };
  purchased?: {
    payments?: Array<{ product_key?: string; status?: string; amount?: number; currency?: string }>;
    subscriptions?: Array<{ product_key?: string; status?: string }>;
  };
  fix_requests?: Array<{ product_key?: string; status?: string; priority?: string; title?: string; studio_task_status?: string }>;
  onboarding?: Array<{ product_key?: string; status?: string; task_type?: string; title?: string }>;
  monitoring?: Array<{ domain?: string; site_url?: string; status?: string; last_checked_at?: string }>;
  dashboard_ready?: boolean;
};

function productLabel(key = "") {
  return key.replaceAll("_", " ") || "Product";
}

export default async function CustomerPage({ searchParams }: { searchParams?: Promise<Record<string, string | string[] | undefined>> }) {
  const params = (await searchParams) || {};
  const tokenValue = params.token;
  const token = Array.isArray(tokenValue) ? tokenValue[0] : tokenValue;
  const data = token ? await fetchJson(`/customer/dashboard/${encodeURIComponent(token)}`) : null;
  const dashboard: Dashboard | null = data?.dashboard || null;
  const payments = dashboard?.purchased?.payments || [];
  const subscriptions = dashboard?.purchased?.subscriptions || [];
  const fixes = dashboard?.fix_requests || [];
  const onboarding = dashboard?.onboarding || [];
  const monitoring = dashboard?.monitoring || [];
  const activeProducts = [...payments, ...subscriptions].slice(0, 4);

  return (
    <div className="shell">
      <header className="nav">
        <div className="brand"><span className="mark">vø</span> Rescue Customer</div>
        <nav className="navlinks"><a href="/">Product</a><a href="/status">Status</a></nav>
      </header>
      <main id="main" className="main">
        <section className="band">
          <div className="eyebrow">Customer dashboard</div>
          <h1>{dashboard?.dashboard_ready ? "Your rescue workspace" : "Secure customer access"}</h1>
          <p className="lede">
            {dashboard?.dashboard_ready
              ? "Track your purchased product, onboarding, fix queue, and monitoring status from one focused workspace."
              : "Open the private customer link from your Vøiddo Rescue onboarding email to view site-specific work."}
          </p>
          <div className="actions">
            <a className="button primary" href="mailto:support@voiddorescue.com">Support</a>
            <a className="button secondary" href="/status">System status</a>
          </div>

          <div className="metric-grid">
            <div className="metric"><strong>{activeProducts.length}</strong><span>Active products</span></div>
            <div className="metric"><strong>{fixes.length}</strong><span>Fix requests</span></div>
            <div className="metric"><strong>{onboarding.length}</strong><span>Onboarding steps</span></div>
            <div className="metric"><strong>{monitoring.length}</strong><span>Monitoring targets</span></div>
          </div>

          <div className="grid customer-grid">
            <div className="panel">
              <h2>Products</h2>
              {(activeProducts.length ? activeProducts : [{ product_key: "No active product yet", status: token ? "pending" : "private link required" }]).map((item, index) => (
                <div className="row compact-row" key={`${item.product_key}-${index}`}>
                  <span className="tag">{index + 1}</span>
                  <span>{productLabel(item.product_key)}</span>
                  <span className="score">{item.status || "ready"}</span>
                </div>
              ))}
            </div>
            <div className="panel">
              <h2>Fix Queue</h2>
              {(fixes.length ? fixes : [{ title: "No fix request open", status: "clear", studio_task_status: "ready" }]).map((item, index) => (
                <div className="row compact-row" key={`${item.title}-${index}`}>
                  <span className="tag">{item.priority || "fix"}</span>
                  <span>{item.title}</span>
                  <span className="score">{item.status || item.studio_task_status}</span>
                </div>
              ))}
            </div>
            <div className="panel">
              <h2>Monitoring</h2>
              {(monitoring.length ? monitoring : [{ domain: "No monitor attached", status: "pending" }]).map((item, index) => (
                <div className="row compact-row" key={`${item.domain}-${index}`}>
                  <span className="tag">{index + 1}</span>
                  <span>{item.domain || item.site_url}</span>
                  <span className="score">{item.status}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="panel">
            <h2>Onboarding</h2>
            {(onboarding.length ? onboarding : [
              { task_type: "audit", title: "Review the current public audit", status: dashboard?.dashboard_ready ? "ready" : "waiting" },
              { task_type: "fix", title: "Confirm the first visible issue to fix", status: dashboard?.dashboard_ready ? "queued" : "waiting" },
              { task_type: "monitoring", title: "Attach monitoring after checkout", status: dashboard?.dashboard_ready ? "ready" : "waiting" },
            ]).map((item, index) => (
              <div className="row" key={`${item.task_type}-${index}`}>
                <span className="tag">{index + 1}</span>
                <span>{item.title}</span>
                <span className="score">{item.status}</span>
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
