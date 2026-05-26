export default async function AuditPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return (
    <div className="shell">
      <header className="nav"><div className="brand"><span className="mark">vø</span> Rescue Audit</div><nav className="navlinks"><a href="/">Product</a><a href="/status">Status</a></nav></header>
      <main id="main" className="main">
        <section className="band">
          <div className="eyebrow">Public non-invasive website check</div>
          <h1>Audit {slug}</h1>
          <p className="lede">This page shows how Rescue presents visible website issues without fearmongering or hidden vulnerability claims.</p>
          <div className="panel">
            <h2>Top Issues</h2>
            <div className="issue"><strong>Possible enquiry path issue.</strong><br />A public browser session may not find a reliable contact path.</div>
            <div className="issue"><strong>Mobile CTA needs verification.</strong><br />Primary customer action may be hard to reach on a small screen.</div>
            <div className="issue"><strong>Search snippet may be incomplete.</strong><br />Title or meta description should be checked before outreach.</div>
          </div>
          <div className="actions">
            <a className="button primary" href="https://rescue.voiddo.com">Fix this issue today</a>
            <a className="button secondary" href="https://rescue.voiddo.com">Start monitoring</a>
          </div>
          <p className="lede" style={{fontSize: 14}}>Legal note: this is a public non-invasive website check from a normal browser session. It does not claim hidden security vulnerabilities.</p>
        </section>
      </main>
    </div>
  );
}
