import { House, MessageSquareText, Settings } from "lucide-react";
import { NavLink } from "react-router-dom";

import { useAuth } from "../../hooks/useAuth";

const navItems = [
  { href: "/dashboard", icon: House, label: "Dashboard" },
  { href: "/chat", icon: MessageSquareText, label: "Chat" },
  { href: "/settings", icon: Settings, label: "Settings" },
] as const;

export function Sidebar() {
  const { user } = useAuth();

  return (
    <aside className="organic-panel organic-panel-strong h-fit p-4 md:sticky md:top-6 lg:w-[280px]">
      <div className="mb-8 flex items-center gap-3 px-2">
        <div className="flex h-12 w-12 items-center justify-center rounded-[var(--radius-leaf)] bg-[var(--organic-muted)] text-[var(--organic-primary)] shadow-[var(--shadow-soft)]">
          {user?.email?.slice(0, 1).toUpperCase() ?? "H"}
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-[var(--organic-foreground)]">
            {user?.email ?? "Guest"}
          </div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--organic-muted-text)]">
            Dog owner
          </div>
        </div>
      </div>

      <nav className="flex flex-col gap-2">
        {navItems.map(({ href, icon: Icon, label }) => (
          <NavLink
            className={({ isActive }) =>
              [
                "flex items-center gap-3 rounded-full px-4 py-3 text-sm font-semibold transition duration-300",
                isActive
                  ? "bg-[var(--organic-primary)] text-[#f3f4f1]"
                  : "text-[var(--organic-muted-text)] hover:bg-[var(--organic-muted)] hover:text-[var(--organic-foreground)]",
              ].join(" ")
            }
            key={href}
            to={href}
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
