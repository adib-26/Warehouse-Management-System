import React, { Suspense } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import Sidebar from "./Sidebar";
import ErrorBoundary from "./ErrorBoundary";

const Dashboard = React.lazy(() => import("./pages/Dashboard"));
const Products = React.lazy(() => import("./pages/Products"));
const Stock = React.lazy(() => import("./pages/Stock"));
const Activity = React.lazy(() => import("./pages/Activity"));

function PageFallback() {
  return (
    <div className="card" style={{ padding: 24 }}>
      <div className="muted" style={{ marginBottom: 8 }}>Loading...</div>
      <div style={{ display: "grid", gap: 8 }}>
        <div style={{ height: 12, width: "40%", background: "rgba(255,255,255,0.04)", borderRadius: 6 }} />
        <div style={{ height: 10, width: "60%", background: "rgba(255,255,255,0.03)", borderRadius: 6 }} />
        <div style={{ height: 160, background: "rgba(255,255,255,0.02)", borderRadius: 8 }} />
      </div>
    </div>
  );
}

export default function App() {
  return (
    <div className="container">
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "12px 0",
          borderBottom: "1px solid rgba(255,255,255,0.04)",
          marginBottom: 16,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: 8,
              background: "linear-gradient(135deg, #2563eb, #1d4ed8)",
              display: "grid",
              placeItems: "center",
              fontWeight: 800,
              color: "white",
              fontSize: "0.85rem",
            }}
          >
            NL
          </div>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <span style={{ fontSize: 14, fontWeight: 700 }}>NovaLedger</span>
            <span className="muted" style={{ fontSize: 11 }}>Inventory Management</span>
          </div>
        </div>
      </header>

      <div className="app-shell">
        <aside className="sidebar" style={{ padding: 16 }}>
          <Sidebar />
        </aside>

        <main
          style={{
            backgroundColor: "var(--bg-surface-dark)",
            color: "var(--text-dark)",
            minHeight: "100vh",
            padding: "24px",
            borderRadius: 12,
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
