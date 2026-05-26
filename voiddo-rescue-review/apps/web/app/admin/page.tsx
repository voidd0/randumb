const metrics = [
  ["0", "leads total"],
  ["0", "qualified"],
  ["0", "audit pages"],
  ["0", "payments"],
  ["0", "emails queued"],
  ["0", "emails sent"],
  ["0", "human review"],
  ["5", "kill switches"],
];

export default function AdminPage() {
  return (
    <div className="shell">
      <header className="nav"><div className="brand"><span className="mark">vø</span> Rescue Admin</div><nav className="navlinks"><a href="/">Product</a><a href="/status">Status</a></nav></header>
      <main id="main" className="dashboard">
        <aside className="sidebar">
          <div className="eyebrow">Control room</div>
          <h1 style={{fontSize: 34, lineHeight: 1.05}}>Pipeline is gated</h1>
          <p className="lede" style={{fontSize: 15}}>Live sends, auto-replies, and Paddle provisioning stay paused until launch gates pass.</p>
        </aside>
        <section className="content">
          <div className="metric-grid">
            {metrics.map(([value, label]) => <div className="metric" key={label}><strong>{value}</strong><span>{label}</span></div>)}
          </div>
          <div className="panel">
            <h2>Kill Switches</h2>
            {["pause scanning", "pause outreach", "pause auto-replies", "pause Paddle provisioning", "pause all workers"].map((item) => (
              <div className="row" key={item}><span className="tag">on</span><span>{item}</span><span className="score">safe</span></div>
            ))}
          </div>
          <div className="panel">
            <h2>First Live Batch</h2>
            <p className="lede" style={{fontSize: 16}}>No live batch has been approved. First day cap is 20 emails total and 5 emails/hour/domain after DNS, mail auth, suppression, unsubscribe, audit page, and Paddle tests pass.</p>
          </div>
        </section>
      </main>
    </div>
  );
}
