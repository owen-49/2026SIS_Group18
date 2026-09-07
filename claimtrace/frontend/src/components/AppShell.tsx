import { useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { Icon, type IconName } from "./Icon";

const navigation: { to: string; label: string; icon: IconName; end?: boolean }[] = [
  { to: "/audit", label: "Batch audit", icon: "audit" },
  { to: "/verify", label: "Review claims", icon: "verify" },
];

export function AppShell() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="app-shell">
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
          <strong>ClaimTrace for Overleaf</strong>
          <p>Review references as you write.</p>
          <Link className="text-button" to="/extension-setup">Set up extension <Icon name="arrow" size={15} /></Link>
        </div>

      </aside>

      {menuOpen && <button className="sidebar-scrim" aria-label="Close menu" onClick={() => setMenuOpen(false)} />}

      <section className="app-content">
        <header className="topbar">
          <button className="icon-button mobile-menu" aria-label="Open menu" onClick={() => setMenuOpen(true)}>
            <Icon name="menu" />
          </button>
          <Link className="help-button" to="/docs">Help <Icon name="external" size={13} /></Link>
        </header>
        <main className="content"><Outlet /></main>
      </section>
    </div>
  );
}
