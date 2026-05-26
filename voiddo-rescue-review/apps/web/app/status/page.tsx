export default function StatusPage() {
  return (
    <div className="shell">
      <header className="nav"><div className="brand"><span className="mark">vø</span> Rescue Status</div><nav className="navlinks"><a href="/">Product</a><a href="/admin">Admin</a></nav></header>
      <main id="main" className="main">
        <section className="band">
          <div className="eyebrow">Launch gate status</div>
          <h1>Gated, monitored, not live outreach ready</h1>
          <p className="lede">Checkout is ready, mail auth is passing, and warmup is scheduled, but recent bounce/rate-limit signals keep sends blocked until the safety window clears.</p>
          <div className="actions">
            <a className="button primary" href="/r/demo">View audit</a>
            <a className="button secondary" href="/">Open product</a>
          </div>
          <div className="grid">
            <div className="tile"><h2>API</h2><p>Configured health endpoint and Paddle webhook route.</p></div>
            <div className="tile"><h2>Scanner</h2><p>Safe public checks only. No admin paths, no exploit probes, no form spam.</p></div>
            <div className="tile"><h2>Outreach</h2><p>Paused until DNS, mail auth, unsubscribe, suppression, and dry-run previews pass.</p></div>
          </div>
        </section>
      </main>
    </div>
  );
}
