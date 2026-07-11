import {
  HomeIcon,
  CubeIcon,
  ArchiveBoxIcon,
  ClipboardDocumentListIcon,
  TruckIcon,
  ArrowDownTrayIcon,
  ArrowUpTrayIcon,
  UserGroupIcon,
  UsersIcon,
  ShieldCheckIcon,
  DocumentMagnifyingGlassIcon,
  ArrowRightStartOnRectangleIcon,
} from "@heroicons/react/24/outline";
import { NavLink } from "react-router-dom";
import { useAuth } from "./AuthContext";

export default function Sidebar() {
  const { user, can, logout } = useAuth();
  const linkClasses = ({ isActive }) => `nav-item ${isActive ? "active" : ""}`;
  const iconStyle = { width: 18, height: 18 };

  return (
    <nav aria-label="Primary navigation" style={{ display: "flex", flexDirection: "column" }}>
      {can("reports", "read") && (
        <div className="sidebar-section">
          <div className="sidebar-label">Overview</div>
          <NavLink to="/dashboard" className={linkClasses}>
            <HomeIcon style={iconStyle} />
            <span>Dashboard</span>
          </NavLink>
        </div>
      )}

      {(can("products", "read") || can("stock", "read")) && (
        <div className="sidebar-section">
          <div className="sidebar-label">Inventory</div>
          {can("products", "read") && (
            <NavLink to="/products" className={linkClasses}>
              <CubeIcon style={iconStyle} />
              <span>Products</span>
            </NavLink>
          )}
          {can("stock", "read") && (
            <NavLink to="/stock" className={linkClasses}>
              <ArchiveBoxIcon style={iconStyle} />
              <span>Stock Adjust</span>
            </NavLink>
          )}
        </div>
      )}

      {(can("inbound", "read") || can("outbound", "read") || can("suppliers", "read") || can("customers", "read")) && (
        <div className="sidebar-section">
          <div className="sidebar-label">Supply Chain</div>
          {can("inbound", "read") && (
            <NavLink to="/inbound" className={linkClasses}>
              <ArrowDownTrayIcon style={iconStyle} />
              <span>Inbound</span>
            </NavLink>
          )}
          {can("outbound", "read") && (
            <NavLink to="/outbound" className={linkClasses}>
              <ArrowUpTrayIcon style={iconStyle} />
              <span>Outbound</span>
            </NavLink>
          )}
          {can("suppliers", "read") && (
            <NavLink to="/suppliers" className={linkClasses}>
              <TruckIcon style={iconStyle} />
              <span>Suppliers</span>
            </NavLink>
          )}
          {can("customers", "read") && (
            <NavLink to="/customers" className={linkClasses}>
              <UserGroupIcon style={iconStyle} />
              <span>Customers</span>
            </NavLink>
          )}
        </div>
      )}

      {can("reports", "read") && (
        <div className="sidebar-section">
          <div className="sidebar-label">Reports</div>
          <NavLink to="/activity" className={linkClasses}>
            <ClipboardDocumentListIcon style={iconStyle} />
            <span>Activity Log</span>
          </NavLink>
          <NavLink to="/audit" className={linkClasses}>
            <DocumentMagnifyingGlassIcon style={iconStyle} />
            <span>Audit Log</span>
          </NavLink>
        </div>
      )}

      {can("admin", "read") && (
        <div className="sidebar-section">
          <div className="sidebar-label">Administration</div>
          <NavLink to="/users" className={linkClasses}>
            <UsersIcon style={iconStyle} />
            <span>Users</span>
          </NavLink>
          <NavLink to="/permissions" className={linkClasses}>
            <ShieldCheckIcon style={iconStyle} />
            <span>Permissions</span>
          </NavLink>
        </div>
      )}

      <div className="sidebar-section" style={{ marginTop: "auto", borderTop: "1px solid var(--border)", paddingTop: 12 }}>
        <div style={{ padding: "4px 12px 10px" }}>
          <div style={{ fontWeight: 600, fontSize: "0.8125rem" }}>{user?.full_name || user?.username}</div>
          <div className="muted" style={{ fontSize: "0.7rem", textTransform: "capitalize" }}>{user?.role}</div>
        </div>
        <button className="nav-item" onClick={logout} style={{ width: "100%", background: "none", border: "none", cursor: "pointer", textAlign: "left" }}>
          <ArrowRightStartOnRectangleIcon style={iconStyle} />
          <span>Sign Out</span>
        </button>
      </div>

      <style>{`
        .nav-item {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 9px 12px;
          border-radius: 8px;
          color: var(--text-secondary);
          text-decoration: none;
          font-size: 0.875rem;
          font-weight: 500;
          transition: all 150ms ease;
          margin: 1px 0;
        }
        .nav-item:hover {
          background: rgba(255, 255, 255, 0.05);
          color: var(--text-primary);
        }
        .nav-item.active {
          background: rgba(59, 130, 246, 0.12);
          color: var(--accent-400);
          font-weight: 600;
        }
        .nav-item svg {
          flex-shrink: 0;
          opacity: 0.7;
        }
        .nav-item.active svg {
          opacity: 1;
        }
      `}</style>
    </nav>
  );
}
