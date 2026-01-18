import {
  HomeIcon,
  CubeIcon,
  ArchiveBoxIcon,
  ClipboardDocumentListIcon,
} from "@heroicons/react/24/outline"
import { NavLink } from "react-router-dom"

export default function Sidebar() {
  const linkClasses = ({ isActive }) =>
    `flex items-center gap-1 px-2 py-1 rounded transition-colors ${
      isActive ? "bg-brand-light text-white" : "hover:text-brand-light"
    }`

  return (
    <aside className="w-44 bg-brand-dark text-white min-h-screen p-4">
      <h2 className="text-base font-bold mb-6">📦 Inventory</h2>
      <nav className="space-y-2 text-xs">
        <NavLink to="/dashboard" className={linkClasses}>
          <HomeIcon className="h-3 w-3" />
          Dashboard
        </NavLink>
        <NavLink to="/products" className={linkClasses}>
          <CubeIcon className="h-3 w-3" />
          Products
        </NavLink>
        <NavLink to="/stock" className={linkClasses}>
          <ArchiveBoxIcon className="h-3 w-3" />
          Stock
        </NavLink>
        <NavLink to="/activity" className={linkClasses}>
          <ClipboardDocumentListIcon className="h-3 w-3" />
          Activity
        </NavLink>
      </nav>
    </aside>
  )
}