import { NavLink } from "react-router-dom";
import { useAuth } from "./AuthContext";

export default function Sidebar({ onNavigate }) {
  const { user, can, logout } = useAuth();
  const linkClasses = ({ isActive }) => `nav-item ${isActive ? "active" : ""}`;
  const handleNavigate = () => onNavigate?.();

  return (
    <nav aria-label="Primary navigation" style={{ display: "flex", flexDirection: "column" }}>
      {can("reports", "read") && (
        <div className="sidebar-section">
          <div className="sidebar-label">Overview</div>
          <NavLink to="/dashboard" className={linkClasses} onClick={handleNavigate}>Dashboard</NavLink>
        </div>
      )}

      {(can("products", "read") || can("stock", "read")) && (
        <div className="sidebar-section">
          <div className="sidebar-label">Inventory</div>
          {can("products", "read") && (
            <NavLink to="/products" className={linkClasses} onClick={handleNavigate}>Products</NavLink>
          )}
          {can("stock", "read") && (
            <NavLink to="/stock" className={linkClasses} onClick={handleNavigate}>Stock Adjust</NavLink>
          )}
        </div>
      )}

      {(can("inbound", "read") || can("outbound", "read") || can("suppliers", "read") || can("customers", "read")) && (
        <div className="sidebar-section">
          <div className="sidebar-label">Supply Chain</div>
          {can("inbound", "read") && (
            <NavLink to="/inbound" className={linkClasses} onClick={handleNavigate}>Inbound</NavLink>
          )}
          {can("outbound", "read") && (
            <NavLink to="/outbound" className={linkClasses} onClick={handleNavigate}>Outbound</NavLink>
          )}
          {can("suppliers", "read") && (
            <NavLink to="/suppliers" className={linkClasses} onClick={handleNavigate}>Suppliers</NavLink>
          )}
          {can("customers", "read") && (
            <NavLink to="/customers" className={linkClasses} onClick={handleNavigate}>Customers</NavLink>
          )}
        </div>
      )}

      {can("reports", "read") && (
        <div className="sidebar-section">
          <div className="sidebar-label">Reports</div>
          <NavLink to="/activity" className={linkClasses} onClick={handleNavigate}>Activity Log</NavLink>
          <NavLink to="/forecasts" className={linkClasses} onClick={handleNavigate}>Forecasts</NavLink>
          <NavLink to="/audit" className={linkClasses} onClick={handleNavigate}>Audit Log</NavLink>
        </div>
      )}

      {can("admin", "read") && (
        <div className="sidebar-section">
          <div className="sidebar-label">Administration</div>
          <NavLink to="/users" className={linkClasses} onClick={handleNavigate}>Users</NavLink>
          <NavLink to="/permissions" className={linkClasses} onClick={handleNavigate}>Permissions</NavLink>
          {can("outbound", "read") && (
            <NavLink to="/warehouses" className={linkClasses} onClick={handleNavigate}>Warehouses</NavLink>
          )}
        </div>
      )}

      <div className="sidebar-section" style={{ marginTop: "auto", borderTop: "1px solid var(--border)", paddingTop: 12 }}>
        <div style={{ padding: "4px 12px 10px" }}>
          <div style={{ fontWeight: 600, fontSize: "0.8125rem" }}>{user?.full_name || user?.username}</div>
          <div className="muted" style={{ fontSize: "0.7rem", textTransform: "capitalize" }}>{user?.role}</div>
        </div>
        <button className="nav-item" onClick={logout} style={{ width: "100%", background: "none", border: "none", cursor: "pointer", textAlign: "left", fontFamily: "inherit" }}>
          Sign Out
        </button>
      </div>
    </nav>
  );
}
