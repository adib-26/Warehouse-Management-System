// frontend/src/App.jsx
import React, { Suspense, useState, useMemo } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import Sidebar from "./Sidebar";
import ErrorBoundary from "./ErrorBoundary";

const Dashboard = React.lazy(() => import("./pages/Dashboard"));
const Products  = React.lazy(() => import("./pages/Products"));
const Stock     = React.lazy(() => import("./pages/Stock"));
const Activity  = React.lazy(() => import("./pages/Activity"));

function PageFallback() {
  return (
    <div role="status" aria-live="polite" className="card" style={{ padding: 24 }}>
      <div className="muted" style={{ marginBottom: 8 }}>Loading content…</div>
      <div style={{ display: "grid", gap: 8 }}>
        <div style={{ height: 12, width: "40%", background: "rgba(0,0,0,0.06)", borderRadius: 6 }} />
        <div style={{ height: 10, width: "60%", background: "rgba(0,0,0,0.04)", borderRadius: 6 }} />
        <div style={{ height: 160, width: "100%", background: "rgba(0,0,0,0.03)", borderRadius: 8 }} />
      </div>
    </div>
  );
}

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const mainClass = useMemo(() => "main-content", []);

  return (
    <div className="container">
      <style>{`
        /* App-level subtle animations (purely visual, respects reduced motion) */

        @keyframes appFadeIn {
          from { opacity: 0; transform: translateY(8px); }
          to { opacity: 1; transform: translateY(0); }
        }

        @keyframes headerReveal {
          from { opacity: 0; transform: translateY(-6px); }
          to { opacity: 1; transform: translateY(0); }
        }

        @keyframes logoShimmer {
          0% { transform: translateX(-120%); }
          100% { transform: translateX(120%); }
        }

        @keyframes sidebarSlide {
          from { opacity: 0; transform: translateX(-8px); }
          to { opacity: 1; transform: translateX(0); }
        }

        @keyframes cardFloat {
          0% { transform: translateY(0); }
          50% { transform: translateY(-6px); }
          100% { transform: translateY(0); }
        }

        @keyframes popIn {
          from { transform: scale(0.98); opacity: 0; }
          to { transform: scale(1); opacity: 1; }
        }

        @keyframes skeletonShimmer {
          0% { background-position: -200% 0; }
          100% { background-position: 200% 0; }
        }

        @keyframes drawLine { to { stroke-dashoffset: 0; } }

        /* Apply entrance to container */
        .container {
          animation: appFadeIn 420ms cubic-bezier(.2,.9,.2,1) both;
        }

        /* Header reveal */
        .header {
          animation: headerReveal 420ms ease both;
          will-change: transform, opacity;
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 12px;
          padding: 8px 0;
        }

        /* Brand and logo shimmer */
        .brand { display: flex; gap: 12px; align-items: center; }
        .logo {
          position: relative;
          overflow: hidden;
          border-radius: 8px;
          transition: transform 200ms ease, filter 300ms ease;
          display: inline-grid;
          place-items: center;
          width: clamp(3.5rem, 6rem, 8rem);
          height: clamp(3.5rem, 6rem, 8rem);
          font-weight: 700;
          background: linear-gradient(180deg, rgba(255,255,255,0.02), transparent);
        }
        .logo::after {
          content: "";
          position: absolute;
          top: 0;
          left: -120%;
          width: 40%;
          height: 100%;
          background: linear-gradient(90deg, transparent, rgba(255,255,255,0.04), transparent);
          transform: skewX(-18deg);
          animation: logoShimmer 1.6s linear infinite;
          pointer-events: none;
          mix-blend-mode: overlay;
        }

        /* Sidebar slide-in */
        .sidebar {
          animation: sidebarSlide 420ms cubic-bezier(.2,.9,.2,1) both;
          will-change: transform, opacity;
        }

        /* Main content transitions */
        .main-content {
          transition: background-color 300ms ease, color 300ms ease;
        }

        /* Card hover lift (subtle) */
        .card {
          transition: transform 260ms cubic-bezier(.2,.9,.2,1), box-shadow 260ms ease;
          will-change: transform;
        }
        .card:hover {
          animation: cardFloat 1400ms ease-in-out infinite;
          box-shadow: 0 18px 40px rgba(2,6,23,0.55);
        }

        /* Pop-in for small text elements */
        .muted, .brand span {
          animation: popIn 360ms cubic-bezier(.2,.9,.2,1) both;
        }

        /* PageFallback skeleton shimmer */
        .card > div > div > div,
        .card > div > div > div + div,
        .card > div > div > div + div + div {
          background: linear-gradient(90deg, rgba(255,255,255,0.02) 0%, rgba(255,255,255,0.04) 50%, rgba(255,255,255,0.02) 100%);
          background-size: 200% 100%;
          animation: skeletonShimmer 1.2s linear infinite;
        }

        /* Sparkline draw helper (if used elsewhere) */
        .sparkline polyline, .sparkline path {
          stroke-dasharray: 260;
          stroke-dashoffset: 260;
          animation: drawLine 900ms ease forwards 120ms;
        }

        /* Respect reduced motion */
        @media (prefers-reduced-motion: reduce) {
          .container, .header, .sidebar, .card, .logo::after, .muted, .brand span, .sparkline polyline {
            animation: none !important;
            transition: none !important;
          }
        }
      `}</style>

      <header className="header" role="banner">
        <div className="brand" aria-hidden>
          <div className="logo">NL</div>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <span style={{ fontSize: 14 }}>NovaLedger</span>
            <span className="muted" style={{ fontSize: 12 }}>Inventory dashboard</span>
          </div>
        </div>

        {/* Right side: contact info */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
          <span style={{ fontSize: 14, fontWeight: 600 }}>📞 +60 12‑345 6789</span>
          <a href="mailto:support@novaledger.com" className="muted" style={{ fontSize: 12 }}>
            support@novaledger.com
          </a>
        </div>
      </header>

      <div className="app-shell" style={{ alignItems: "start" }}>
        <aside
          id="sidebar"
          className="sidebar"
          aria-hidden={!sidebarOpen && window.innerWidth < 880}
        >
          <Sidebar />
        </aside>

        {/* main: use design tokens for background and text to avoid white imbalance */}
        <main
          className={mainClass}
          id="main"
          tabIndex={-1}
          style={{
            backgroundColor: "var(--bg-surface-dark)",
            color: "var(--text-dark)",
            minHeight: "100vh",
            padding: "24px",
          }}
        >
          <ErrorBoundary>
            <Suspense fallback={<PageFallback />}>
              <Routes>
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/products" element={<Products />} />
                <Route path="/stock" element={<Stock />} />
                <Route path="/activity" element={<Activity />} />

                <Route
                  path="*"
                  element={
                    <div className="card" style={{ padding: 24 }}>
                      <h2>Page not found</h2>
                      <p className="muted">The page you requested does not exist.</p>
                    </div>
                  }
                />
              </Routes>
            </Suspense>
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
