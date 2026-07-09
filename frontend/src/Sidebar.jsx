import { HomeIcon, CubeIcon, ArchiveBoxIcon, ClipboardDocumentListIcon } from "@heroicons/react/24/outline";
import { NavLink } from "react-router-dom";

export default function Sidebar() {
  const linkClasses = ({ isActive }) =>
    `nav-item ${isActive ? "active" : ""}`;

  return (
    <nav aria-label="Primary navigation" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <NavLink to="/dashboard" className={linkClasses}>
        <HomeIcon style={{ width: 18, height: 18 }} aria-hidden />
        <span>Dashboard</span>
      </NavLink>
      <NavLink to="/products" className={linkClasses}>
        <CubeIcon style={{ width: 18, height: 18 }} aria-hidden />
        <span>Products</span>
      </NavLink>
      <NavLink to="/stock" className={linkClasses}>
        <ArchiveBoxIcon style={{ width: 18, height: 18 }} aria-hidden />
        <span>Stock</span>
      </NavLink>
      <NavLink to="/activity" className={linkClasses}>
        <ClipboardDocumentListIcon style={{ width: 18, height: 18 }} aria-hidden />
        <span>Activity</span>
      </NavLink>

      <style>{`
        .nav-item {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 10px 12px;
          border-radius: 8px;
          color: var(--text-dark);
          text-decoration: none;
          font-size: 0.9rem;
          transition: background 160ms ease;
        }
        .nav-item:hover {
          background: rgba(37, 99, 235, 0.06);
        }
        .nav-item.active {
          background: linear-gradient(90deg, color-mix(in srgb, var(--accent) 14%, transparent), color-mix(in srgb, var(--accent-600) 8%, transparent));
          color: white;
        }
        .nav-item svg {
          flex-shrink: 0;
        }
        @media (prefers-color-scheme: light) {
          .nav-item { color: var(--text-light); }
        }
      `}</style>
    </nav>
  );
}
