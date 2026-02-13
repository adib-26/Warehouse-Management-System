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
    <section className="dashboard-root">
      <style>{`
        /* Subtle entrance for the whole section */
        .dashboard-root {
          animation: fadeInUp 420ms ease both;
        }

        @keyframes fadeInUp {
          from { opacity: 0; transform: translateY(6px); }
          to { opacity: 1; transform: translateY(0); }
        }

        /* Card surface (keeps your dark theme, no white) */
        .card {
          background: var(--bg-surface-dark);
          color: var(--text-dark);
          border-radius: 12px;
          padding: 14px;
          box-shadow: 0 6px 18px rgba(2,6,23,0.45);
          transition: transform 220ms cubic-bezier(.2,.9,.2,1), box-shadow 220ms ease;
          will-change: transform;
        }

        /* Lift on hover */
        .card:hover {
          transform: translateY(-6px);
          box-shadow: 0 18px 40px rgba(2,6,23,0.55);
        }

        /* Small accent bar on top of cards */
        .card.accent-top {
          border-top: 4px solid var(--accent);
        }

        /* Live badge pulse */
        .live-badge {
          font-size: 12px;
          color: var(--muted);
          padding: 6px 10px;
          border-radius: 8px;
          background: color-mix(in srgb, var(--text-dark) 6%, transparent);
          display: inline-grid;
          grid-auto-flow: column;
          gap: 8px;
          align-items: center;
        }

        .live-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: var(--accent);
          box-shadow: 0 0 0 rgba(37,99,235,0.12);
          animation: pulse 1400ms infinite;
        }

        @keyframes pulse {
          0% { transform: scale(1); box-shadow: 0 0 0 0 rgba(37,99,235,0.18); }
          70% { transform: scale(1.18); box-shadow: 0 0 0 8px rgba(37,99,235,0); }
          100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(37,99,235,0); }
        }

        /* Icon container shimmer */
        .icon-pill {
          width: 44px;
          height: 44px;
          border-radius: 10px;
          display: grid;
          place-items: center;
          background: linear-gradient(90deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01));
          position: relative;
          overflow: hidden;
        }

        .icon-pill::after {
          content: "";
          position: absolute;
          left: -60%;
          top: 0;
          width: 60%;
          height: 100%;
          background: linear-gradient(90deg, transparent, rgba(255,255,255,0.03), transparent);
          transform: skewX(-18deg);
          animation: shimmer 1.6s linear infinite;
        }

        @keyframes shimmer {
          to { left: 160%; }
        }

        /* Number pop animation */
        .stat-number {
          font-size: 22px;
          font-weight: 700;
          color: var(--text-dark);
          display: inline-block;
          transform-origin: center;
          animation: popIn 420ms cubic-bezier(.2,.9,.2,1);
        }

        @keyframes popIn {
          from { transform: scale(0.96); opacity: 0; }
          to { transform: scale(1); opacity: 1; }
        }

        /* Sparkline line glow */
        .sparkline polyline {
          filter: drop-shadow(0 6px 12px rgba(37,99,235,0.12));
          stroke-linecap: round;
          stroke-linejoin: round;
        }

        /* Muted text token */
        .muted {
          color: var(--muted);
        }

        /* Responsive tweaks */
        @media (max-width: 720px) {
          .card { padding: 12px; border-radius: 10px; }
          .icon-pill { width: 40px; height: 40px; }
        }
      `}</style>

      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 16, marginBottom: 20 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: "1.5rem", letterSpacing: "-0.01em" }}>Dashboard Overview</h1>
          <p className="muted" style={{ margin: "6px 0 0 0" }}>Snapshot of inventory and activity</p>
        </div>

        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <div className="live-badge">
            <span className="live-dot" aria-hidden />
            <span className="muted">Live</span>
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
          className="card accent-top"
          aria-live="polite"
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", gap: 12 }}>
            <div>
              <h2 style={{ margin: 0, fontSize: "0.95rem" }}>Total Products</h2>
              <p className="muted" style={{ margin: "8px 0 0 0" }}>Number of SKUs</p>
            </div>

            <div className="icon-pill" aria-hidden>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
                <path d="M3 7.5L12 3l9 4.5v6L12 21 3 13.5v-6z" stroke="white" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
          </div>

          <div style={{ marginTop: 12 }}>
            <span className="stat-number">{stats.products}</span>
          </div>
        </div>

        <div
          className="card"
          style={{ borderTop: "4px solid color-mix(in srgb, var(--accent) 60%, black 10%)" }}
          aria-live="polite"
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", gap: 12 }}>
            <div>
              <h2 style={{ margin: 0, fontSize: "0.95rem" }}>Total Stock</h2>
              <p className="muted" style={{ margin: "8px 0 0 0" }}>Sum of quantities</p>
            </div>

            <div className="icon-pill" aria-hidden>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
                <path d="M3 7h18M3 12h18M3 17h18" stroke="white" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
          </div>

          <div style={{ marginTop: 12 }}>
            <span className="stat-number">{stats.stock}</span>
          </div>
        </div>

        <div
          className="card"
          style={{ borderTop: "4px solid color-mix(in srgb, var(--accent) 60%, transparent)" }}
          aria-live="polite"
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", gap: 12 }}>
            <div>
              <h2 style={{ margin: 0, fontSize: "0.95rem" }}>Activity Logs</h2>
              <p className="muted" style={{ margin: "8px 0 0 0" }}>Recent events</p>
            </div>

            <div className="icon-pill" aria-hidden>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
                <path d="M12 6v6l4 2" stroke="white" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
                <circle cx="12" cy="12" r="9" stroke="white" strokeWidth="1.2" />
              </svg>
            </div>
          </div>

          <div style={{ marginTop: 12 }}>
            <span className="stat-number">{stats.activity}</span>
          </div>
        </div>
      </div>

      {/* Chart / trend card */}
      <div className="card" style={{ padding: 18 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
          <h2 style={{ margin: 0, fontSize: "1rem" }}>Equity Trend</h2>
          <div style={{ fontSize: 12, color: "var(--muted)" }}>Last 30 days</div>
        </div>

        <div style={{ marginTop: 12, display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
          {/* Simple sparkline placeholder built with SVG — no external libs */}
          <div style={{ flex: "1 1 320px", minWidth: 220 }}>
            <svg className="sparkline" viewBox="0 0 120 40" width="100%" height="40" preserveAspectRatio="none" aria-hidden>
              <defs>
                <linearGradient id="g" x1="0" x2="1">
                  <stop offset="0" stopColor="rgba(96,165,250,0.18)" />
                  <stop offset="1" stopColor="rgba(37,99,235,0.06)" />
                </linearGradient>
              </defs>

              {/* background area */}
              <path d="M0 30 L20 24 L40 18 L60 12 L80 16 L100 10 L120 8 L120 40 L0 40 Z" fill="url(#g)" />

              {/* animated line (stroke-dash for draw effect) */}
              <polyline
                points="0,30 20,24 40,18 60,12 80,16 100,10 120,8"
                fill="none"
                stroke="var(--accent)"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                style={{
                  strokeDasharray: 260,
                  strokeDashoffset: 260,
                  animation: "drawLine 900ms ease forwards 120ms"
                }}
              />
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

      <style>{`
        @keyframes drawLine {
          to { stroke-dashoffset: 0; }
        }
      `}</style>
    </section>
  );
}
