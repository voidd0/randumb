export default function CustomerPage() {
  return (
    <div className="shell">
      <header className="nav"><div className="brand"><span className="mark">vø</span> Rescue Customer</div><nav className="navlinks"><a href="/">Product</a><a href="/status">Status</a></nav></header>
      <main id="main" className="main">
        <section className="band">
          <div className="eyebrow">Customer dashboard</div>
          <h1>Your site rescue</h1>
          <p className="lede">Track the paid product, current audit, fix request, monitoring status, and read-only WordPress connection from one place.</p>
          <div className="actions">
            <a className="button primary" href="mailto:support@voiddorescue.com">Support</a>
            <a className="button secondary" href="/r/demo">View audit</a>
          </div>
          <div className="grid">
            <div className="tile"><h2>Audit</h2><p>Current public check and issue list.</p></div>
            <div className="tile"><h2>Fix Request</h2><p>Status, priority, evidence, and next action.</p></div>
            <div className="tile"><h2>Monitoring</h2><p>Recurring checks and reporting status.</p></div>
          </div>
          <div className="panel">
            <h2>Onboarding steps</h2>
            <div className="row"><span className="tag">1</span><span>Review the current audit and top issues</span><span className="score">ready</span></div>
            <div className="row"><span className="tag">2</span><span>Install the read-only WordPress agent when needed</span><span className="score">optional</span></div>
            <div className="row"><span className="tag">3</span><span>Track fix request and monitoring updates</span><span className="score">queued</span></div>
          </div>
        </section>
      </main>
    </div>
  );
}
