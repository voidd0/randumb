import { fetchJson } from "../../lib/api";

export default async function UnsubscribePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const result = await fetchJson(`/unsubscribe/${encodeURIComponent(token)}`);
  const confirmed = Boolean(result?.suppressed);
  return (
    <div className="shell">
      <header className="nav"><div className="brand"><span className="mark">vø</span> Rescue</div><nav className="navlinks"><a href="/">Product</a><a href="/status">Status</a></nav></header>
      <main id="main" className="main">
        <section className="band">
          <div className="eyebrow">Unsubscribe</div>
          <h1>{confirmed ? "Suppression confirmed" : "Suppression link unavailable"}</h1>
          <p className="lede">{confirmed ? "This address has been removed from Vøiddo Rescue outreach." : "This unsubscribe link could not be confirmed. Contact support and we will remove the address manually."}</p>
          <div className="actions">
            <a className="button primary" href="/status">Unsubscribe status</a>
            <a className="button secondary" href="/">Product</a>
          </div>
          <div className="panel"><div className="row"><span className="tag">status</span><span>{confirmed ? "suppressed" : "manual support available"}</span><span className="score">{confirmed ? "done" : "review"}</span></div></div>
          <p className="muted">Public non-invasive website checks only. No action is required.</p>
        </section>
      </main>
    </div>
  );
}
