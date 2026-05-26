export default function Page() {
  return (
    <div className="shell">
      <header className="nav">
        <div className="brand"><span className="mark">vø</span> Vøiddo Rescue</div>
        <nav className="navlinks" aria-label="Primary">
          <a href="/admin">Admin</a>
          <a href="/status">Status</a>
          <a href="/r/demo">Demo audit</a>
        </nav>
      </header>
      <main id="main" className="main">
        <section className="hero">
          <div>
            <div className="eyebrow">Public checks. Proof first. Dry-run gated.</div>
            <h1>Vøiddo Rescue</h1>
            <p className="lede">
              Finds visible website problems, turns them into proof-based audit pages, queues compliant outreach,
              and routes paid fixes into onboarding and monitoring.
            </p>
            <div className="actions">
              <a className="button primary" href="/admin">Open pipeline</a>
              <a className="button secondary" href="/r/demo">View audit format</a>
            </div>
          </div>
          <div className="console" aria-label="Pipeline preview">
            <div className="console-head"><span>autonomous revenue chain</span><span className="pulse" /></div>
            <div className="rows">
              {[
                ["scan", "public browser check", "safe"],
                ["audit", "top issues + screenshots", "ready"],
                ["mail", "dry-run outreach queue", "paused"],
                ["reply", "classification + review gate", "armed"],
                ["pay", "Paddle webhook provisioning", "paused"],
              ].map(([tag, text, score]) => (
                <div className="row" key={tag}>
                  <span className="tag">{tag}</span>
                  <span className="status">{text}</span>
                  <span className="score">{score}</span>
                </div>
              ))}
            </div>
          </div>
        </section>
        <section className="band grid" aria-label="Capabilities">
          <div className="tile"><h2>Safe Scanner</h2><p>Homepage availability, HTTPS, screenshots, metadata, contact paths, and dead public CTAs only.</p></div>
          <div className="tile"><h2>Controlled Outreach</h2><p>Templates, suppression, unsubscribe, rate limits, dry-run previews, and launch flag before live sends.</p></div>
          <div className="tile"><h2>Paid Workflow</h2><p>Paddle webhooks create customers, onboarding, fix requests, and ongoing monitoring tasks.</p></div>
        </section>
      </main>
      <footer className="footer">Built by vøiddo — a small studio shipping AI-flavoured products, free dev tools, Chrome extensions and weird browser games.</footer>
    </div>
  );
}
