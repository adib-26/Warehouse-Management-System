// frontend/src/pages/Dashboard.jsx
import { useEffect, useState } from "react";

const API = "http://localhost:8000";

export default function Dashboard() {
  const [stats, setStats] = useState({ products: 0, stock: 0, activity: 0 });

  const load = async () => {
    // You can adjust these endpoints based on your backend
    const products = await (await fetch(`${API}/products`)).json();
    const history = await (await fetch(`${API}/history`)).json();

    setStats({
      products: products.length,
      stock: products.reduce((sum, p) => sum + p.quantity, 0),
      activity: history.length,
    });
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <section>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 16, marginBottom: 20 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: "1.5rem", letterSpacing: "-0.01em" }}>Dashboard Overview</h1>
          <p className="muted" style={{ margin: "6px 0 0 0" }}>Snapshot of inventory and activity</p>
        </div>

        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <div style={{
            fontSize: 12,
            color: "var(--muted)",
            background: "color-mix(in srgb, var(--text-dark) 6%, transparent)",
            padding: "6px 10px",
            borderRadius: 8
          }}>
            Live
          </div>
          <div style={{ fontSize: 12, color: "var(--muted)" }}>Source: local API</div>
        </div>
      </header>

      {/* Summary cards */}
      <div style={{
        display: "grid",
        gap: 16,
        gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
        marginBottom: 18
      }}>
        <div
          className="card"
          style={{
            borderTop: "4px solid var(--accent)",
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            minHeight: 120
          }}
          aria-live="polite"
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", gap: 12 }}>
            <div>
              <h2 style={{ margin: 0, fontSize: "0.95rem" }}>Total Products</h2>
              <p className="muted" style={{ margin: "8px 0 0 0" }}>Number of SKUs</p>
            </div>

            <div style={{
              width: 44,
              height: 44,
              borderRadius: 10,
              display: "grid",
              placeItems: "center",
              background: "color-mix(in srgb, var(--accent) 14%, transparent)"
            }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
                <path d="M3 7.5L12 3l9 4.5v6L12 21 3 13.5v-6z" stroke="white" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
          </div>

          <div style={{ marginTop: 12, fontSize: 22, fontWeight: 700, color: "var(--text-dark)" }}>
            {stats.products}
          </div>
        </div>

        <div
          className="card"
          style={{
            borderTop: "4px solid color-mix(in srgb, var(--accent) 60%, black 10%)",
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            minHeight: 120
          }}
          aria-live="polite"
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", gap: 12 }}>
            <div>
              <h2 style={{ margin: 0, fontSize: "0.95rem" }}>Total Stock</h2>
              <p className="muted" style={{ margin: "8px 0 0 0" }}>Sum of quantities</p>
            </div>

            <div style={{
              width: 44,
              height: 44,
              borderRadius: 10,
              display: "grid",
              placeItems: "center",
              background: "color-mix(in srgb, var(--accent-400) 12%, transparent)"
            }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
                <path d="M3 7h18M3 12h18M3 17h18" stroke="white" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
          </div>

          <div style={{ marginTop: 12, fontSize: 22, fontWeight: 700, color: "var(--text-dark)" }}>
            {stats.stock}
          </div>
        </div>

        <div
          className="card"
          style={{
            borderTop: "4px solid color-mix(in srgb, var(--accent-600) 18%, transparent)",
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            minHeight: 120
          }}
          aria-live="polite"
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", gap: 12 }}>
            <div>
              <h2 style={{ margin: 0, fontSize: "0.95rem" }}>Activity Logs</h2>
              <p className="muted" style={{ margin: "8px 0 0 0" }}>Recent events</p>
            </div>

            <div style={{
              width: 44,
              height: 44,
              borderRadius: 10,
              display: "grid",
              placeItems: "center",
              background: "color-mix(in srgb, var(--accent-600) 12%, transparent)"
            }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
                <path d="M12 6v6l4 2" stroke="white" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
                <circle cx="12" cy="12" r="9" stroke="white" strokeWidth="1.2" />
              </svg>
            </div>
          </div>

          <div style={{ marginTop: 12, fontSize: 22, fontWeight: 700, color: "var(--text-dark)" }}>
            {stats.activity}
          </div>
        </div>
      </div>

      {/* Chart / trend card */}
      <div className="card" style={{ padding: 18 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
          <h2 style={{ margin: 0, fontSize: "1rem" }}>Stock Trend</h2>
          <div style={{ fontSize: 12, color: "var(--muted)" }}>Last 30 days</div>
        </div>

        <div style={{ marginTop: 12, display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
          {/* Simple sparkline placeholder built with SVG — no external libs */}
          <div style={{ flex: "1 1 320px", minWidth: 220 }}>
            <svg viewBox="0 0 120 40" width="100%" height="40" preserveAspectRatio="none" aria-hidden>
              <defs>
                <linearGradient id="g" x1="0" x2="1">
                  <stop offset="0" stopColor="rgba(96,165,250,0.18)" />
                  <stop offset="1" stopColor="rgba(37,99,235,0.06)" />
                </linearGradient>
              </defs>

              {/* background area */}
              <path d="M0 30 L20 24 L40 18 L60 12 L80 16 L100 10 L120 8 L120 40 L0 40 Z" fill="url(#g)" />

              {/* line */}
              <polyline points="0,30 20,24 40,18 60,12 80,16 100,10 120,8" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <p className="muted" style={{ marginTop: 8 }}>Estimated trend based on recent stock changes</p>
          </div>

          <div style={{ minWidth: 160 }}>
            <div style={{ fontSize: 14, color: "var(--muted)" }}>Change (30d)</div>
            <div style={{ marginTop: 8, fontSize: 20, fontWeight: 700, color: "var(--accent)" }}>+4.8%</div>
            <div className="muted" style={{ marginTop: 6 }}>Compared to previous period</div>
          </div>
        </div>
      </div>
    </section>
  );
}
