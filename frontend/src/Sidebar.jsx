import { HomeIcon, CubeIcon, ArchiveBoxIcon, ClipboardDocumentListIcon, TruckIcon, ArrowDownTrayIcon } from "@heroicons/react/24/outline";
import { NavLink } from "react-router-dom";

export default function Sidebar() {
  const linkClasses = ({ isActive }) => `nav-item ${isActive ? "active" : ""}`;

  return (
    <nav aria-label="Primary navigation" style={{ display: "flex", flexDirection: "column" }}>
      <div className="sidebar-section">
        <div className="sidebar-label">Overview</div>
        <NavLink to="/dashboard" className={linkClasses}>
          <HomeIcon style={{ width: 18, height: 18 }} />
          <span>Dashboard</span>
        </NavLink>
      </div>

      <div className="sidebar-section">
        <div className="sidebar-label">Inventory</div>
        <NavLink to="/products" className={linkClasses}>
          <CubeIcon style={{ width: 18, height: 18 }} />
          <span>Products</span>
        </NavLink>
        <NavLink to="/stock" className={linkClasses}>
          <ArchiveBoxIcon style={{ width: 18, height: 18 }} />
          <span>Stock Adjust</span>
        </NavLink>
      </div>

      <div className="sidebar-section">
        <div className="sidebar-label">Supply Chain</div>
        <NavLink to="/inbound" className={linkClasses}>
          <ArrowDownTrayIcon style={{ width: 18, height: 18 }} />
          <span>Inbound</span>
        </NavLink>
        <NavLink to="/suppliers" className={linkClasses}>
          <TruckIcon style={{ width: 18, height: 18 }} />
          <span>Suppliers</span>
        </NavLink>
      </div>

      <div className="sidebar-section">
        <div className="sidebar-label">Reports</div>
        <NavLink to="/activity" className={linkClasses}>
          <ClipboardDocumentListIcon style={{ width: 18, height: 18 }} />
          <span>Activity Log</span>
        </NavLink>
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
