import React, { Suspense } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import Sidebar from "./Sidebar";
import ErrorBoundary from "./ErrorBoundary";
import { AuthProvider, useAuth } from "./AuthContext";
import { API_ROOT } from "./api";
import Login from "./pages/Login";

const Dashboard = React.lazy(() => import("./pages/Dashboard"));
const Products = React.lazy(() => import("./pages/Products"));
const Stock = React.lazy(() => import("./pages/Stock"));
const Activity = React.lazy(() => import("./pages/Activity"));
const Suppliers = React.lazy(() => import("./pages/Suppliers"));
const Inbound = React.lazy(() => import("./pages/Inbound"));
const Outbound = React.lazy(() => import("./pages/Outbound"));
const Warehouses = React.lazy(() => import("./pages/Warehouses"));
const Customers = React.lazy(() => import("./pages/Customers"));
const Users = React.lazy(() => import("./pages/Users"));
const Permissions = React.lazy(() => import("./pages/Permissions"));
const AuditLog = React.lazy(() => import("./pages/AuditLog"));
const Forecasting = React.lazy(() => import("./pages/Forecasting"));

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

function PermissionRoute({ module, children }) {
  const { can } = useAuth();

  if (can(module, "read")) return children;

  return (
    <section className="card">
      <div className="card-body empty-state">
        <h2 style={{ margin: "0 0 8px", fontSize: "1.25rem" }}>Access denied</h2>
        <p className="muted">Your account does not have access to this page.</p>
      </div>
    </section>
  );
}

function AppShell() {
  const { user, loading } = useAuth();
  const [systemOnline, setSystemOnline] = React.useState(null);

  React.useEffect(() => {
    let active = true;

    const checkHealth = async () => {
      try {
        const response = await fetch(`${API_ROOT}/health`, { cache: "no-store" });
        if (!response.ok) throw new Error("Health check failed");
        const health = await response.json();
        if (active) setSystemOnline(health.status === "ok");
      } catch {
        if (active) setSystemOnline(false);
      }
    };

    checkHealth();
    const timer = window.setInterval(checkHealth, 30_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

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
          <div aria-label={systemOnline === false ? "System offline" : systemOnline ? "System online" : "Checking system status"} style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: systemOnline === false ? "var(--red)" : systemOnline ? "var(--green)" : "var(--muted)",
            boxShadow: systemOnline === false ? "0 0 6px rgba(239, 68, 68, 0.4)" : systemOnline ? "0 0 6px rgba(16, 185, 129, 0.4)" : "none",
          }} />
          <span style={{ fontSize: "0.8125rem", color: "var(--muted)" }}>
            {systemOnline === false ? "System Offline" : systemOnline ? "System Online" : "Checking System"}
          </span>
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
                <Route path="/dashboard" element={<PermissionRoute module="reports"><Dashboard /></PermissionRoute>} />
                <Route path="/products" element={<PermissionRoute module="products"><Products /></PermissionRoute>} />
                <Route path="/stock" element={<PermissionRoute module="stock"><Stock /></PermissionRoute>} />
                <Route path="/inbound" element={<PermissionRoute module="inbound"><Inbound /></PermissionRoute>} />
                <Route path="/outbound" element={<PermissionRoute module="outbound"><Outbound /></PermissionRoute>} />
                <Route path="/warehouses" element={<PermissionRoute module="outbound"><Warehouses /></PermissionRoute>} />
                <Route path="/suppliers" element={<PermissionRoute module="suppliers"><Suppliers /></PermissionRoute>} />
                <Route path="/customers" element={<PermissionRoute module="customers"><Customers /></PermissionRoute>} />
                <Route path="/activity" element={<PermissionRoute module="reports"><Activity /></PermissionRoute>} />
                <Route path="/forecasts" element={<PermissionRoute module="reports"><Forecasting /></PermissionRoute>} />
                <Route path="/users" element={<PermissionRoute module="admin"><Users /></PermissionRoute>} />
                <Route path="/permissions" element={<PermissionRoute module="admin"><Permissions /></PermissionRoute>} />
                <Route path="/audit" element={<PermissionRoute module="reports"><AuditLog /></PermissionRoute>} />
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
