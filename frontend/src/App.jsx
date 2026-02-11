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
