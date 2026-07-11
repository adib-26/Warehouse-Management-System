import React, { Suspense } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import Sidebar from "./Sidebar";
import ErrorBoundary from "./ErrorBoundary";
import { AuthProvider, useAuth } from "./AuthContext";
import Login from "./pages/Login";

const Dashboard = React.lazy(() => import("./pages/Dashboard"));
const Products = React.lazy(() => import("./pages/Products"));
const Stock = React.lazy(() => import("./pages/Stock"));
const Activity = React.lazy(() => import("./pages/Activity"));
const Suppliers = React.lazy(() => import("./pages/Suppliers"));
const Inbound = React.lazy(() => import("./pages/Inbound"));
const Outbound = React.lazy(() => import("./pages/Outbound"));
const Customers = React.lazy(() => import("./pages/Customers"));
const Users = React.lazy(() => import("./pages/Users"));
const Permissions = React.lazy(() => import("./pages/Permissions"));
const AuditLog = React.lazy(() => import("./pages/AuditLog"));

function PageFallback() {
  return (
    <div className="card">
      <div className="card-body" style={{ padding: 32 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div className="spinner" />
          <span className="muted">Loading...</span>
        </div>
      </div>
    </div>
  );
}

function AppShell() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div style={{ minHeight: "100vh", display: "grid", placeItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div className="spinner" />
          <span className="muted">Loading...</span>
        </div>
      </div>
    );
  }

  if (!user) {
    return <Login />;
  }

  return (
    <div className="container">
      <header style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "16px 0",
        borderBottom: "1px solid var(--border)",
        marginBottom: 0,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{
            width: 38,
            height: 38,
            borderRadius: 10,
            background: "linear-gradient(135deg, #3b82f6, #2563eb)",
            display: "grid",
            placeItems: "center",
            fontWeight: 800,
            color: "white",
            fontSize: "0.8rem",
            letterSpacing: "-0.02em",
            boxShadow: "0 2px 8px rgba(37, 99, 235, 0.3)",
          }}>
            NL
          </div>
          <div>
            <div style={{ fontSize: "0.9375rem", fontWeight: 700, letterSpacing: "-0.01em" }}>NovaLedger</div>
            <div style={{ fontSize: "0.75rem", color: "var(--muted)" }}>Warehouse Management</div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: "var(--green)",
            boxShadow: "0 0 6px rgba(16, 185, 129, 0.4)",
          }} />
          <span style={{ fontSize: "0.8125rem", color: "var(--muted)" }}>System Online</span>
        </div>
      </header>

      <div className="app-shell">
        <aside className="sidebar">
          <Sidebar />
        </aside>

        <main style={{ padding: "24px 0", minHeight: "calc(100vh - 80px)" }}>
          <ErrorBoundary>
            <Suspense fallback={<PageFallback />}>
              <Routes>
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
                <Route path="/login" element={<Navigate to="/dashboard" replace />} />
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/products" element={<Products />} />
                <Route path="/stock" element={<Stock />} />
                <Route path="/inbound" element={<Inbound />} />
                <Route path="/outbound" element={<Outbound />} />
                <Route path="/suppliers" element={<Suppliers />} />
                <Route path="/customers" element={<Customers />} />
                <Route path="/activity" element={<Activity />} />
                <Route path="/users" element={<Users />} />
                <Route path="/permissions" element={<Permissions />} />
                <Route path="/audit" element={<AuditLog />} />
                <Route path="*" element={
                  <div className="card">
                    <div className="card-body empty-state">
                      <h2 style={{ margin: "0 0 8px", fontSize: "1.25rem" }}>Page not found</h2>
                      <p className="muted">The page you requested does not exist.</p>
                    </div>
                  </div>
                } />
              </Routes>
            </Suspense>
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  );
}
