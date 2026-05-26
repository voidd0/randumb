export default function CustomerPage() {
  return (
    <div className="shell">
      <header className="nav"><div className="brand"><span className="mark">vø</span> Rescue Customer</div><nav className="navlinks"><a href="/">Product</a><a href="/status">Status</a></nav></header>
      <main id="main" className="main">
        <section className="band">
          <div className="eyebrow">Customer dashboard MVP</div>
          <h1>Your site rescue</h1>
          <div className="grid">
            <div className="tile"><h2>Audit</h2><p>Current public check and issue list.</p></div>
            <div className="tile"><h2>Fix Request</h2><p>Status, priority, evidence, and next action.</p></div>
            <div className="tile"><h2>Monitoring</h2><p>Recurring checks and reporting status.</p></div>
          </div>
          <div className="actions">
            <a className="button primary" href="mailto:support@voiddorescue.com">Support</a>
            <a className="button secondary" href="/r/demo">View audit</a>
          </div>
        </section>
      </main>
    </div>
  );
}
