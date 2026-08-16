import { useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { usingMockApi } from "../api/client";
import { Icon, type IconName } from "./Icon";

const navigation: { to: string; label: string; icon: IconName; end?: boolean }[] = [
  { to: "/", label: "Overview", icon: "spark", end: true },
  { to: "/library", label: "Paper library", icon: "library" },
  { to: "/upload", label: "Upload papers", icon: "upload" },
  { to: "/verify", label: "Verify a claim", icon: "verify" },
  { to: "/audit", label: "Batch audit", icon: "audit" },
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
          <span className="eyebrow">Browser extension</span>
          <strong>Audit while you write</strong>
          <p>Link your Overleaf bibliography and inspect every citation in context.</p>
          <Link className="text-button" to="/extension-setup">Setup guide <Icon name="arrow" size={15} /></Link>
        </div>

        <div className="profile-row">
          <span className="avatar">LL</span>
          <span><strong>Research workspace</strong><small>Local project</small></span>
          <Icon name="chevron" size={16} />
        </div>
      </aside>

      {menuOpen && <button className="sidebar-scrim" aria-label="Close menu" onClick={() => setMenuOpen(false)} />}

      <section className="app-content">
        <header className="topbar">
          <button className="icon-button mobile-menu" aria-label="Open menu" onClick={() => setMenuOpen(true)}>
            <Icon name="menu" />
          </button>
          <Link className="topbar-status" to="/docs#demo-workspace" title="Learn about the current workspace mode">
            <span className={usingMockApi ? "status-dot status-demo" : "status-dot"} />
            {usingMockApi ? "Demo workspace" : "API connected"}
          </Link>
          <Link className="help-button" to="/docs">Help & docs</Link>
        </header>
        <main className="content"><Outlet /></main>
      </section>
    </div>
  );
}
