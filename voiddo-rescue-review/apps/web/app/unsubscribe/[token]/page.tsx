export default async function UnsubscribePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return (
    <div className="shell">
      <header className="nav"><div className="brand"><span className="mark">vø</span> Rescue</div><nav className="navlinks"><a href="/">Product</a><a href="/status">Status</a></nav></header>
      <main id="main" className="main">
        <section className="band">
          <div className="eyebrow">Unsubscribe</div>
          <h1>Suppression request received</h1>
          <p className="lede">This page confirms the unsubscribe path for Vøiddo Rescue outreach. The API stores suppression by token during live operation.</p>
          <div className="actions">
            <a className="button primary" href="/status">Unsubscribe status</a>
            <a className="button secondary" href="/">Product</a>
          </div>
          <div className="panel"><div className="row"><span className="tag">token</span><span>{token.slice(0, 8)}...</span><span className="score">received</span></div></div>
          <p className="muted">Public non-invasive website checks only. No action is required.</p>
        </section>
      </main>
    </div>
  );
}
