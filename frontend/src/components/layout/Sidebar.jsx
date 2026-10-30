import { House, Landmark } from "lucide-react";
import { Link, useLocation } from "wouter";
import { cn } from "../../lib/utils";
import { BUILD_NAV, DOMAIN_JOURNEYS, OBSERVE_NAV } from "../../lib/navigation";

const TEXT = "rgba(255, 255, 255, 0.92)";
const TEXT_MUTED = "rgba(255, 255, 255, 0.55)";
const ACTIVE_BG = "rgba(255, 255, 255, 0.14)";
const ACTIVE_RING = "rgba(255, 255, 255, 0.22)";

const linkClass =
  "flex items-center gap-2.5 px-2 py-1.5 rounded-[var(--radius)] font-sans text-[14px] transition-colors cursor-pointer";

function linkStyle(active) {
  return active
    ? { background: ACTIVE_BG, color: "#ffffff", boxShadow: `inset 0 0 0 1px ${ACTIVE_RING}` }
    : { color: TEXT };
}

function NavLink({ href, icon: Icon, label, active }) {
  return (
    <Link
      href={href}
      className={cn(linkClass, active ? "font-medium" : "nav-item-dark")}
      style={linkStyle(active)}
    >
      <Icon size={18} style={{ flexShrink: 0 }} />
      <span>{label}</span>
    </Link>
  );
}

function NavSection({ title, items }) {
  const [location] = useLocation();
  return (
    <div className="mb-4">
      <p
        className="font-sans text-[11px] uppercase tracking-widest mb-1 px-2"
        style={{ color: TEXT_MUTED }}
      >
        {title}
      </p>
      <ul className="space-y-0.5">
        {items.map((item) => (
          <li key={item.id}>
            <NavLink
              href={item.path}
              icon={item.icon}
              label={item.label}
              active={location === item.path}
            />
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function Sidebar() {
  const [location] = useLocation();

  return (
    <aside
      className="sidebar-dark flex flex-col shrink-0"
      style={{
        width: "220px",
        minHeight: "100vh",
        background: "#002855",
        borderRight: "1px solid rgba(255, 255, 255, 0.08)",
        padding: "1rem 0.75rem",
        position: "sticky",
        top: 0,
        height: "100vh",
        overflowY: "auto",
      }}
    >
      <div className="flex items-center gap-2.5 mb-6 px-1">
        <div
          className="flex items-center justify-center rounded-lg shrink-0"
          style={{ width: 32, height: 32, background: "rgba(255, 255, 255, 0.12)" }}
        >
          <Landmark size={18} style={{ color: "#ffffff" }} />
        </div>
        <div className="min-w-0">
          <p className="font-serif leading-tight truncate" style={{ fontSize: "15px", color: "#ffffff" }}>
            Mortgage Agentic Workbench
          </p>
          <p
            className="font-sans uppercase tracking-widest truncate"
            style={{ fontSize: "11px", color: TEXT_MUTED }}
          >
            Agentic OS for Mortgage
          </p>
        </div>
      </div>

      <div className="mb-4">
        <NavLink href="/" icon={House} label="Command Center" active={location === "/"} />
      </div>

      <NavSection title="Domain Journeys" items={DOMAIN_JOURNEYS} />
      <NavSection title="Build" items={BUILD_NAV} />
      <NavSection title="Observe" items={OBSERVE_NAV} />

      <div className="flex-1" />

      <div
        className="mt-4 px-2 py-3 rounded-[var(--radius)]"
        style={{ background: "rgba(255, 255, 255, 0.08)" }}
      >
        <div className="flex items-center gap-1.5 mb-0.5">
          <span className="inline-block rounded-full" style={{ width: 7, height: 7, background: "#22c55e" }} />
          <span className="font-sans font-medium" style={{ fontSize: "12px", color: "#ffffff" }}>
            Agent Active
          </span>
        </div>
        <p className="font-sans" style={{ fontSize: "11px", color: TEXT, marginLeft: "14px" }}>
          Firstsource Agent Engine
        </p>
        <p className="font-sans" style={{ fontSize: "10px", color: TEXT_MUTED, marginLeft: "14px" }}>
          Powered by Firstsource AgenticOS
        </p>
      </div>
    </aside>
  );
}
