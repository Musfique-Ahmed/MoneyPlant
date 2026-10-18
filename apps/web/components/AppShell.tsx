"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode } from "react";
import { clsx } from "clsx";
import {
  LayoutDashboard,
  Database,
  Calculator,
  GitCompare,
  ShieldCheck,
  Sparkles,
  Settings,
  Sprout,
} from "lucide-react";
import { ThemeToggle } from "@/components/ThemeToggle";

const NAV: Array<{ href: string; label: string; icon: ReactNode }> = [
  { href: "/dashboard", label: "Dashboard", icon: <LayoutDashboard size={16} /> },
  { href: "/data", label: "Data", icon: <Database size={16} /> },
  { href: "/simulator", label: "Simulator", icon: <Calculator size={16} /> },
  { href: "/compare", label: "Compare", icon: <GitCompare size={16} /> },
  { href: "/decisions", label: "Decisions", icon: <ShieldCheck size={16} /> },
  { href: "/assistant", label: "Assistant", icon: <Sparkles size={16} /> },
  { href: "/settings", label: "Settings", icon: <Settings size={16} /> },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="grid min-h-screen grid-cols-[14rem_1fr] bg-surface">
      <aside className="flex flex-col border-r border-line bg-surface-sunken">
        <div className="flex h-14 items-center gap-2 border-b border-line px-4">
          <Sprout size={18} className="text-accent" />
          <span className="text-md font-semibold tracking-tight">MoneyPlant</span>
        </div>
        <nav className="flex flex-1 flex-col gap-0.5 p-2" aria-label="Main">
          {NAV.map((item) => {
            const active = pathname === item.href || pathname.startsWith(item.href + "/");
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={clsx(
                  "flex h-8 items-center gap-2 rounded px-2 text-sm",
                  active
                    ? "bg-accent-soft text-accent"
                    : "text-ink-muted hover:bg-surface hover:text-ink"
                )}
              >
                {item.icon}
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-line p-3 text-2xs text-ink-subtle">
          <div>Engine 0.1.0</div>
          <div>MoneyPlant · single-tenant MVP</div>
        </div>
      </aside>
      <div className="flex min-h-screen min-w-0 flex-col">
        <div className="flex h-14 items-center justify-end gap-2 border-b border-line bg-surface px-6">
          <ThemeToggle />
        </div>
        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  );
}