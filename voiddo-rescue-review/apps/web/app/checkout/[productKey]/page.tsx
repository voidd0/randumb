import { notFound } from "next/navigation";
import { CheckoutClient } from "./CheckoutClient";

type PageProps = {
  params: Promise<{ productKey: string }>;
  searchParams: Promise<{ audit?: string; email?: string }>;
};

async function getCheckoutConfig(productKey: string, audit = "", email = "") {
  const base = process.env.API_INTERNAL_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || "http://api:8080";
  const query = new URLSearchParams();
  if (audit) query.set("audit", audit);
  if (email) query.set("email", email);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  const response = await fetch(`${base}/checkout/config/${productKey}${suffix}`, { cache: "no-store" });
  if (response.status === 404) return null;
  if (!response.ok) {
    return { ok: false, ready: false, product_key: productKey, reason: await response.text() };
  }
  return response.json();
}

export default async function CheckoutPage({ params, searchParams }: PageProps) {
  const { productKey } = await params;
  const { audit = "", email = "" } = await searchParams;
  const config = await getCheckoutConfig(productKey, audit, email);
  if (!config) notFound();

  return (
    <div className="shell">
      <header className="nav">
        <div className="brand"><span className="mark">vø</span> Rescue Checkout</div>
        <nav className="navlinks" aria-label="Checkout"><a href="/">Product</a><a href="/status">Status</a></nav>
      </header>
      <main id="main" className="main">
        {config.ready ? (
          <CheckoutClient config={config} />
        ) : (
          <section className="band">
            <div className="eyebrow">Checkout gated</div>
            <h1>Checkout is not configured</h1>
            <p className="lede">This product is available in the catalog, but Paddle checkout is not enabled for this environment yet.</p>
            <div className="panel"><div className="row"><span className="tag">reason</span><span>{config.reason || "checkout_not_configured"}</span><span className="score">blocked</span></div></div>
          </section>
        )}
      </main>
    </div>
  );
}
