// frontend/src/Sidebar.jsx
import React from "react";
import {
  HomeIcon,
  CubeIcon,
  ArchiveBoxIcon,
  ClipboardDocumentListIcon,
} from "@heroicons/react/24/outline";
import { NavLink } from "react-router-dom";

export default function Sidebar() {
  const linkClasses = ({ isActive }) =>
    `nav-item ${isActive ? "active" : ""}`;

  return (
    <aside className="sidebar compact-sidebar" aria-label="Primary navigation">
      <nav className="nav-list" aria-label="Sidebar">
        <NavLink to="/dashboard" className={linkClasses}>
          <HomeIcon className="icon" aria-hidden />
          <span className="label">Dashboard</span>
        </NavLink>

        <NavLink to="/products" className={linkClasses}>
          <CubeIcon className="icon" aria-hidden />
          <span className="label">Products</span>
        </NavLink>

        <NavLink to="/stock" className={linkClasses}>
          <ArchiveBoxIcon className="icon" aria-hidden />
          <span className="label">Stock</span>
        </NavLink>

        <NavLink to="/activity" className={linkClasses}>
          <ClipboardDocumentListIcon className="icon" aria-hidden />
          <span className="label">Activity</span>
        </NavLink>
      </nav>

      <style jsx>{`
        /* Compact sidebar variant */
        .compact-sidebar {
          padding: 16px;
          border-radius: 12px;
        }

        .nav-list {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .nav-item {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 8px 10px;
          border-radius: 8px;
          color: var(--text-dark);
          text-decoration: none;
          font-size: 0.95rem;
          transition: background var(--transition-fast, 160ms) ease,
            transform var(--transition-fast, 160ms) ease;
        }

        .nav-item:hover,
        .nav-item:focus-visible {
          background-color: rgba(37, 99, 235, 0.06);
          transform: translateY(-1px);
          outline: none;
        }

        .nav-item.active {
          background-color: color-mix(in srgb, var(--accent) 12%, transparent);
          color: white;
        }

        .nav-item .icon {
          width: 18px;
          height: 18px;
          flex: 0 0 18px;
          color: inherit;
        }

        .nav-item .label {
          line-height: 1;
        }

        /* Make sure the sidebar surface is compact but still uses theme tokens */
        .sidebar {
          background-color: var(--bg-surface-dark);
          min-height: 160px;
          box-shadow: var(--elevation-1);
        }

        /* Responsive: collapse spacing on small screens */
        @media (max-width: 880px) {
          .compact-sidebar {
            padding: 12px;
          }
          .nav-item {
            padding: 8px;
            gap: 8px;
          }
          .nav-item .icon {
            width: 16px;
            height: 16px;
            flex: 0 0 16px;
          }
        }

        /* Light mode adjustments */
        @media (prefers-color-scheme: light) {
          .sidebar {
            background-color: var(--bg-surface-light);
          }
          .nav-item {
            color: var(--text-light);
          }
        }
      `}</style>
    </aside>
  );
}
