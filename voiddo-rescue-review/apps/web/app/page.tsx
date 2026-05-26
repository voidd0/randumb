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
        <section className="hero hero-proof">
          <div>
            <div className="eyebrow">Autonomous website rescue for local businesses</div>
            <h1>Vøiddo Rescue</h1>
            <p className="lede">
              Public browser checks, proof audit pages, controlled outreach, Paddle checkout, onboarding,
              fix requests, and monitoring in one gated revenue pipeline.
            </p>
            <div className="actions">
              <a className="button primary" href="/r/demo">View proof audit</a>
              <a className="button secondary" href="/r/demo">View audit format</a>
            </div>
            <div className="trust-strip" aria-label="Safety markers">
              <span>public non-invasive check</span>
              <span>unsubscribe-safe</span>
              <span>Paddle checkout</span>
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
        <section className="band grid" aria-label="How it works">
          <div className="tile"><h2>1. Find visible issues</h2><p>Safe public checks detect availability, HTTPS, metadata, screenshots, contact paths, and dead CTAs.</p></div>
          <div className="tile"><h2>2. Show proof</h2><p>Each qualified lead gets a clear audit page with screenshots, top issues, impact, and repair options.</p></div>
          <div className="tile"><h2>3. Convert carefully</h2><p>Outreach stays template-bound, suppressed, throttled, QA-checked, and blocked until launch gates pass.</p></div>
        </section>
        <section className="band offer-band" aria-label="Pricing">
          <div>
            <div className="eyebrow">Offers</div>
            <h2>Simple paid paths after proof.</h2>
          </div>
          <div className="price-grid">
            <div className="price"><strong>$19/mo</strong><span>Website Monitor</span></div>
            <div className="price"><strong>$99</strong><span>Contact Form Repair</span></div>
            <div className="price"><strong>$149</strong><span>Emergency Website Fix</span></div>
          </div>
        </section>
      </main>
      <footer className="footer">Built by vøiddo — a small studio shipping AI-flavoured products, free dev tools, Chrome extensions and weird browser games.</footer>
    </div>
  );
}
