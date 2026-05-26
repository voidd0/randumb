import { notFound } from "next/navigation";
import { fetchJson } from "../../../lib/api";

type Dashboard = {
  customer: { email?: string; status?: string };
  purchased: {
    payments?: Array<{ product_key: string; status: string; amount?: number; currency?: string }>;
    subscriptions?: Array<{ product_key: string; status: string }>;
  };
  fix_requests?: Array<{ product_key: string; status: string; priority: string; title: string; studio_task_status?: string }>;
  onboarding?: Array<{ product_key: string; status: string; task_type: string; title: string }>;
  monitoring?: Array<{ domain: string; site_url: string; status: string; last_checked_at?: string }>;
};

function productLabel(key?: string) {
  return (key || "rescue").replaceAll("_", " ");
}

function statusLabel(value?: string) {
  return value ? value.replaceAll("_", " ") : "ready";
}

export default async function CustomerTokenDashboard({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const payload = await fetchJson(`/customer/dashboard/${token}`);
  const dashboard = payload?.dashboard as Dashboard | undefined;
  if (!dashboard) notFound();

  const payments = dashboard.purchased?.payments || [];
  const subscriptions = dashboard.purchased?.subscriptions || [];
  const fixes = dashboard.fix_requests || [];
  const onboarding = dashboard.onboarding || [];
  const monitoring = dashboard.monitoring || [];

  return (
    <div className="shell">
      <header className="nav">
        <div className="brand"><span className="mark">vø</span> Rescue Customer</div>
        <nav className="navlinks"><a href="/">Product</a><a href="/status">Status</a></nav>
      </header>
      <main id="main" className="main">
        <section className="band">
          <div className="eyebrow">Private customer view</div>
          <h1 style={{fontSize: 48, lineHeight: 1}}>Your site rescue workspace</h1>
          <p className="lede">A focused view of your purchased plan, fix work, onboarding steps, and active monitoring checks.</p>
          <div className="actions tight">
            <a className="button primary" href="mailto:support@voiddorescue.com">Contact support</a>
            <a className="button secondary" href="/status">System status</a>
          </div>
          <div className="metric-grid audit-meta">
            <div className="metric"><strong>{payments.length + subscriptions.length}</strong><span>products</span></div>
            <div className="metric"><strong>{fixes.length}</strong><span>fix requests</span></div>
            <div className="metric"><strong>{monitoring.length}</strong><span>monitored sites</span></div>
            <div className="metric"><strong>{statusLabel(dashboard.customer?.status)}</strong><span>account</span></div>
          </div>

          <div className="panel">
            <h2>Purchased Products</h2>
            {payments.length || subscriptions.length ? (
              [...payments, ...subscriptions].map((item, index) => (
                <div className="row" key={`${item.product_key}-${index}`}>
                  <span className="tag">{statusLabel(item.status)}</span>
                  <span>{productLabel(item.product_key)}</span>
                  <span className="score">active</span>
                </div>
              ))
            ) : (
              <p className="muted">No paid product is attached to this dashboard yet.</p>
            )}
          </div>

          <div className="panel">
            <h2>Fix Requests</h2>
            {fixes.length ? fixes.map((fix) => (
              <div className="row" key={`${fix.product_key}-${fix.title}`}>
                <span className="tag">{fix.priority}</span>
                <span>{fix.title}</span>
                <span className="score">{statusLabel(fix.status)}</span>
              </div>
            )) : <p className="muted">No fix request is currently open.</p>}
          </div>

          <div className="panel">
            <h2>Monitoring</h2>
            {monitoring.length ? monitoring.map((target) => (
              <div className="row" key={target.domain}>
                <span className="tag">{statusLabel(target.status)}</span>
                <span>{target.domain}</span>
                <span className="score">{target.last_checked_at ? "checked" : "queued"}</span>
              </div>
            )) : <p className="muted">Monitoring will appear after a site is connected to this customer account.</p>}
          </div>

          <div className="panel">
            <h2>Onboarding</h2>
            {onboarding.length ? onboarding.map((step) => (
              <div className="row" key={`${step.task_type}-${step.title}`}>
                <span className="tag">{statusLabel(step.status)}</span>
                <span>{step.title}</span>
                <span className="score">{productLabel(step.product_key)}</span>
              </div>
            )) : (
              <>
                <div className="row"><span className="tag">ready</span><span>Review the latest audit and fix scope</span><span className="score">step 1</span></div>
                <div className="row"><span className="tag">optional</span><span>Connect the read-only WordPress agent when requested</span><span className="score">step 2</span></div>
                <div className="row"><span className="tag">active</span><span>Receive monitoring and repair status updates</span><span className="score">step 3</span></div>
              </>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
