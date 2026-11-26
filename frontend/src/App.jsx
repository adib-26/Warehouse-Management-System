import React, { Suspense } from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import Sidebar from "./Sidebar";
import ErrorBoundary from "./ErrorBoundary";
import ThemeToggle from "./components/ThemeToggle";
import BrandMark from "./components/BrandMark";
import { FeedbackProvider } from "./components/FeedbackProvider";
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
    <div className="card" role="status" aria-live="polite">
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

function Brand() {
  return (
    <div className="app-brand">
      <BrandMark />
      <span className="brand-text">
        <span className="wordmark">
          <span className="wordmark__nova">Nova</span><span className="wordmark__ledger">Ledger</span>
        </span>
        <span className="brand-sub">Warehouse Management</span>
      </span>
    </div>
  );
}

function NavDrawer({ open, onClose }) {
  const ref = React.useRef(null);

  React.useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    else if (!open && dialog.open) dialog.close();
  }, [open]);

  React.useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return undefined;
    dialog.setAttribute("closedby", "any");
    const handleClose = () => onClose();
    dialog.addEventListener("close", handleClose);
    return () => dialog.removeEventListener("close", handleClose);
  }, [onClose]);

  return (
    <dialog ref={ref} className="drawer" id="app-drawer" aria-label="Navigation">
      <div className="drawer__inner">
        <div className="drawer__head">
          <Brand />
          <button type="button" className="icon-btn" aria-label="Close navigation" autoFocus onClick={onClose}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
        <Sidebar onNavigate={onClose} />
      </div>
    </dialog>
  );
}

function AppShell() {
  const { user, loading } = useAuth();
  const [systemOnline, setSystemOnline] = React.useState(null);
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const location = useLocation();

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

  // Close the mobile drawer whenever the route changes.
  React.useEffect(() => { setDrawerOpen(false); }, [location.pathname]);

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

  const statusState = systemOnline === false ? "offline" : systemOnline ? "online" : "checking";
  const statusLabel = systemOnline === false ? "Offline" : systemOnline ? "Online" : "Checking";

  return (
    <div className="container">
      <a className="skip-link" href="#main">Skip to content</a>

      <header className="app-header">
        <div className="app-header__left">
          <button
            type="button"
            className="icon-btn menu-btn"
            aria-label="Open navigation"
            aria-controls="app-drawer"
            aria-expanded={drawerOpen}
            onClick={() => setDrawerOpen(true)}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M3 6h18M3 12h18M3 18h18" />
            </svg>
          </button>
          <Brand />
        </div>
        <div className="app-header__right">
          <p className="app-status" data-state={statusState}>
            <span className="status-dot" data-state={statusState} aria-hidden="true" />
            <span className="app-status__text">System {statusLabel}</span>
          </p>
          <ThemeToggle />
        </div>
      </header>

      <div className="app-shell">
        <aside className="sidebar">
          <Sidebar />
        </aside>

        <main id="main" className="app-main">
          <ErrorBoundary>
            <Suspense fallback={<PageFallback />}>
              <div className="route-view" key={location.pathname}>
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
              </div>
            </Suspense>
          </ErrorBoundary>
        </main>
      </div>

      <NavDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </div>
  );
}

export default function App() {
  return (
    <FeedbackProvider>
      <AuthProvider>
        <AppShell />
      </AuthProvider>
    </FeedbackProvider>
  );
}
