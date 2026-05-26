"use client";

import { useEffect, useMemo, useState } from "react";

type CheckoutConfig = {
  ok: boolean;
  ready: boolean;
  environment: string;
  client_token: string;
  product_key: string;
  price_id: string;
  audit_slug?: string;
  email?: string;
  custom_data: Record<string, string>;
  product: {
    name: string;
    amount: number;
    currency: string;
    mode: string;
  };
};

declare global {
  interface Window {
    Paddle?: {
      Environment?: { set: (environment: "sandbox" | "production") => void };
      Initialize: (config: Record<string, unknown>) => void;
      Checkout: { open: (config: Record<string, unknown>) => void };
    };
  }
}

function loadPaddleScript() {
  return new Promise<void>((resolve, reject) => {
    if (window.Paddle) {
      resolve();
      return;
    }
    const existing = document.querySelector<HTMLScriptElement>('script[src="https://cdn.paddle.com/paddle/v2/paddle.js"]');
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("Paddle.js failed to load")));
      return;
    }
    const script = document.createElement("script");
    script.src = "https://cdn.paddle.com/paddle/v2/paddle.js";
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Paddle.js failed to load"));
    document.head.appendChild(script);
  });
}

export function CheckoutClient({ config }: { config: CheckoutConfig }) {
  const [status, setStatus] = useState("loading");
  const [detail, setDetail] = useState("Preparing secure checkout");
  const formatted = useMemo(() => `${config.product.amount} ${config.product.currency}${config.product.mode === "subscription" ? "/month" : ""}`, [config]);

  useEffect(() => {
    let active = true;
    async function openCheckout() {
      try {
        await loadPaddleScript();
        if (!active || !window.Paddle) return;
        if (config.environment === "sandbox" && window.Paddle.Environment) {
          window.Paddle.Environment.set("sandbox");
        }
        window.Paddle.Initialize({
          token: config.client_token,
          eventCallback: (event: unknown) => {
            if (!active) return;
            const name = typeof event === "object" && event && "name" in event ? String((event as { name: unknown }).name) : "checkout.event";
            setStatus(name);
          },
        });
        window.Paddle.Checkout.open({
          items: [{ priceId: config.price_id, quantity: 1 }],
          customer: config.email ? { email: config.email } : undefined,
          customData: config.custom_data,
          settings: {
            displayMode: "inline",
            variant: "one-page",
            theme: "light",
            locale: "en",
            frameTarget: "paddle-checkout-frame",
            frameInitialHeight: 520,
            frameStyle: "width: 100%; min-width: 312px; background-color: transparent; border: none;",
          },
        });
        setDetail("Checkout loaded. Payment is handled by Paddle.");
      } catch (error) {
        if (!active) return;
        setStatus("checkout_error");
        setDetail(error instanceof Error ? error.message : "Checkout failed to initialize");
      }
    }
    openCheckout();
    return () => {
      active = false;
    };
  }, [config]);

  return (
    <div className="checkout-layout">
      <aside className="checkout-summary">
        <div className="eyebrow">Paddle checkout</div>
        <h1>{config.product.name}</h1>
        <p className="lede">{formatted}</p>
        <div className="row"><span className="tag">product</span><span>{config.product_key.replaceAll("_", " ")}</span><span className="score">ready</span></div>
        <div className="row"><span className="tag">audit</span><span>{config.audit_slug || "none"}</span><span className="score">linked</span></div>
        <div className="row"><span className="tag">status</span><span>{status}</span><span className="score">gated</span></div>
        <p className="muted">Provisioning remains paused until Paddle webhook tests and launch gates pass.</p>
      </aside>
      <section className="checkout-frame-panel" aria-label="Paddle checkout">
        <div id="paddle-checkout-frame" className="checkout-frame"><span>{detail}</span></div>
      </section>
    </div>
  );
}
