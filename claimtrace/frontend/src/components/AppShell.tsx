import { AISettings } from "./AISettings";
import { useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { Icon, type IconName } from "./Icon";

const navigation: { to: string; label: string; icon: IconName; end?: boolean }[] = [
  { to: "/audit", label: "Batch audit", icon: "audit" },
  { to: "/verify", label: "Verify claims", icon: "verify" },
];

export function AppShell() {
  const { pathname } = useLocation();
  const sectionName = pathname.startsWith("/verify") ? "Verify claims" : pathname.startsWith("/audit") ? "Batch audit" : pathname.startsWith("/docs") ? "Guide" : "Extension setup";
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className={`app-shell${pathname.startsWith("/verify") ? " app-shell-verify" : ""}`}>
      <aside className={menuOpen ? "sidebar sidebar-open" : "sidebar"}>
        <div className="brand">
          <span className="brand-mark"><Icon name="shield" size={22} /></span>
          <span>ClaimTrace</span>
        </div>

        <nav className="main-nav" aria-label="Main navigation">
          <p className="nav-label">Workspace</p>
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              end={item.end}
              to={item.to}
              onClick={() => setMenuOpen(false)}
              className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
            >
              <Icon name={item.icon} size={18} />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-card">
          <strong>Set up ClaimTrace in Overleaf</strong>
          <Link className="text-button" to="/extension-setup">Set up extension <Icon name="arrow" size={15} /></Link>
        </div>

      </aside>

      {menuOpen && <button className="sidebar-scrim" aria-label="Close menu" onClick={() => setMenuOpen(false)} />}

      <section className="app-content">
        <header className="topbar">
          <button className="icon-button mobile-menu" aria-label="Open menu" onClick={() => setMenuOpen(true)}>
            <Icon name="menu" />
          </button>
          <div className="topbar-context" aria-hidden="true">Workspace <span>/</span><strong>{sectionName}</strong></div>
          <AISettings />
          <Link className="help-button" to="/docs">Help <Icon name="external" size={13} /></Link>
        </header>
        <main className="content"><Outlet /></main>
      </section>
    </div>
  );
}
