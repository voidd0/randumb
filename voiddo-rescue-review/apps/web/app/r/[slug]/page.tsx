import { notFound } from "next/navigation";
import { fetchJson } from "../../lib/api";

type Issue = {
  severity: string;
  title: string;
  public_text: string;
  recommendation: string;
};

type Screenshot = {
  type: string;
  public_url?: string;
  viewport?: string;
};

function demoAudit(slug: string) {
  if (slug !== "demo") return null;
  return {
    business: { name: "Demo business" },
    domain: "example.com",
    url: "https://example.com",
    checked_at: new Date().toISOString(),
    score: 70,
    summary: "Demo audit page format. Real audit pages are loaded from the Rescue API.",
    issues: [
      { severity: "high", title: "Possible enquiry path issue", public_text: "A public browser session may not find a reliable contact path.", recommendation: "Place a clear contact action above the fold." },
      { severity: "medium", title: "Search snippet may be incomplete", public_text: "The page may be missing a useful meta description.", recommendation: "Add a concise meta description for the service and location." },
    ],
    screenshots: [],
    checkout_links: {},
  };
}

export default async function AuditPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const payload = await fetchJson(`/audits/${slug}`);
  const audit = payload?.audit || demoAudit(slug);
  if (!audit) notFound();

  const issues = (audit.issues || []).slice(0, 3) as Issue[];
  const screenshots = (audit.screenshots || []) as Screenshot[];
  const links = audit.checkout_links || {};

  return (
    <div className="shell">
      <header className="nav"><div className="brand"><span className="mark">vø</span> Rescue Audit</div><nav className="navlinks"><a href="/">Product</a><a href="/status">Status</a></nav></header>
      <main id="main" className="main">
        <section className="band">
          <div className="eyebrow">Public non-invasive website check</div>
          <h1>{audit.business?.name || audit.domain}</h1>
          <p className="lede">{audit.url}</p>
          <div className="metric-grid audit-meta">
            <div className="metric"><strong>{audit.score}</strong><span>score</span></div>
            <div className="metric"><strong>{issues.length}</strong><span>top issues</span></div>
            <div className="metric"><strong>{new Date(audit.checked_at || audit.created_at).toLocaleDateString("en-GB")}</strong><span>checked</span></div>
          </div>
          <div className="panel">
            <h2>Top Issues</h2>
            {issues.length ? issues.map((issue) => (
              <div className="issue" key={`${issue.severity}-${issue.title}`}>
                <span className={`severity ${issue.severity}`}>{issue.severity}</span>
                <strong>{issue.title}</strong>
                <p>{issue.public_text}</p>
                <p className="muted">{issue.recommendation}</p>
              </div>
            )) : <p className="lede">No major visible issue was recorded in this public browser check.</p>}
          </div>
          <div className="panel">
            <h2>Screenshots</h2>
            <div className="screenshot-grid">
              {screenshots.length ? screenshots.map((shot) => (
                <figure className="shot" key={`${shot.type}-${shot.viewport}`}>
                  {shot.public_url ? <img src={shot.public_url} alt={`${shot.type} screenshot`} /> : <div className="shot-missing">stored evidence</div>}
                  <figcaption>{shot.type} · {shot.viewport}</figcaption>
                </figure>
              )) : <p className="lede">Screenshot evidence will appear here after a real scanner job completes.</p>}
            </div>
          </div>
          <div className="actions">
            <a className="button primary" href={links.contact_form_repair || links.emergency_fix || "https://rescue.voiddo.com"}>Fix this issue today</a>
            <a className="button secondary" href={links.monitor_monthly || "https://rescue.voiddo.com"}>Start monitoring</a>
          </div>
          <p className="lede" style={{fontSize: 14}}>Legal note: this is a public non-invasive website check from a normal browser session. It does not claim hidden security vulnerabilities.</p>
        </section>
      </main>
    </div>
  );
}
