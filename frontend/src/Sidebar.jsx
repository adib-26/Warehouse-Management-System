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

        /* Micro-interaction keyframes */
        @keyframes navItemRise {
          from { opacity: 0; transform: translateY(8px) scale(0.995); }
          to { opacity: 1; transform: translateY(0) scale(1); }
        }

        @keyframes iconFloat {
          0% { transform: translateY(0); }
          50% { transform: translateY(-4px); }
          100% { transform: translateY(0); }
        }

        @keyframes activePulse {
          0% { box-shadow: 0 0 0 0 rgba(37,99,235,0.08); }
          60% { box-shadow: 0 8px 20px rgba(37,99,235,0.06); }
          100% { box-shadow: 0 0 0 0 rgba(37,99,235,0); }
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
          transition:
            background var(--transition-fast, 160ms) ease,
            transform var(--transition-fast, 160ms) ease,
            box-shadow var(--transition-fast, 160ms) ease;
          will-change: transform, opacity;
          /* entrance animation for each item (staggered below) */
          animation: navItemRise 420ms cubic-bezier(.2,.9,.2,1) both;
        }

        /* Staggered entrance for nav items */
        .nav-list > .nav-item:nth-child(1) { animation-delay: 40ms; }
        .nav-list > .nav-item:nth-child(2) { animation-delay: 120ms; }
        .nav-list > .nav-item:nth-child(3) { animation-delay: 200ms; }
        .nav-list > .nav-item:nth-child(4) { animation-delay: 280ms; }

        .nav-item:hover,
        .nav-item:focus-visible {
          background-color: rgba(37, 99, 235, 0.06);
          transform: translateY(-2px) scale(1.002);
          outline: none;
        }

        .nav-item.active {
          background: linear-gradient(90deg, color-mix(in srgb, var(--accent) 14%, transparent), color-mix(in srgb, var(--accent-600) 8%, transparent));
          color: white;
          transform: translateY(-2px);
          box-shadow: 0 8px 22px rgba(37,99,235,0.08);
        }

        /* Icon styling and subtle motion */
        .nav-item .icon {
          width: 18px;
          height: 18px;
          flex: 0 0 18px;
          color: inherit;
          display: inline-block;
          transition: transform 260ms ease, opacity 260ms ease;
          will-change: transform, opacity;
        }

        /* Float icon slightly on hover for tactile feel */
        .nav-item:hover .icon,
        .nav-item:focus-visible .icon {
          animation: iconFloat 900ms ease-in-out infinite;
        }

        /* Active icon pulse (single subtle pulse) */
        .nav-item.active .icon {
          animation: none;
          transform: translateY(-2px) scale(1.02);
          filter: drop-shadow(0 6px 18px rgba(37,99,235,0.08));
        }

        /* Add a small decorative ring on active state (animated once) */
        .nav-item.active::after {
          content: "";
          position: absolute;
          left: 8px;
          right: 8px;
          top: 6px;
          bottom: 6px;
          border-radius: 8px;
          pointer-events: none;
          animation: activePulse 900ms ease;
        }

        .nav-item .label {
          line-height: 1;
        }

        /* Make sure the sidebar surface is compact but still uses theme tokens */
        .sidebar {
          background-color: var(--bg-surface-dark);
          min-height: 160px;
          box-shadow: var(--elevation-1);
          position: relative;
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
          .nav-item.active {
            color: white;
          }
        }

        /* Respect reduced motion preference */
        @media (prefers-reduced-motion: reduce) {
          .nav-item,
          .nav-item .icon,
          .nav-item.active::after {
            animation: none !important;
            transition: none !important;
            transform: none !important;
          }
        }
      `}</style>
    </aside>
  );
}
