"use client";

import {
  Activity,
  FlaskConical,
  LayoutDashboard,
  Microscope,
  PlayCircle,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const nav = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/runs", label: "Runs", icon: PlayCircle },
  { href: "/results", label: "Results", icon: Activity },
  { href: "/inspect", label: "Inspect", icon: Microscope },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 border-b border-line/90 bg-canvas/90 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1540px] items-center justify-between gap-4 px-4 py-3 sm:px-6 lg:px-8">
          <Link href="/" className="flex min-w-0 items-center gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-2xl bg-ink text-lime shadow-lg shadow-ink/10">
              <FlaskConical size={21} />
            </span>
            <span className="min-w-0">
              <span className="block truncate text-sm font-black tracking-[-0.02em]">
                AcneLLM Eval Control
              </span>
              <span className="block truncate text-[11px] font-semibold uppercase tracking-[0.18em] text-ink/45">
                localhost · port 3100
              </span>
            </span>
          </Link>
          <nav className="flex items-center gap-1 overflow-x-auto rounded-2xl border border-line bg-panel p-1 shadow-sm">
            {nav.map((item) => {
              const active =
                item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-2 whitespace-nowrap rounded-xl px-3 py-2 text-sm font-bold transition ${
                    active
                      ? "bg-ink text-white shadow-sm"
                      : "text-ink/55 hover:bg-canvas hover:text-ink"
                  }`}
                >
                  <Icon size={15} />
                  <span className="hidden sm:inline">{item.label}</span>
                </Link>
              );
            })}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-[1540px] px-4 py-7 sm:px-6 lg:px-8">
        {children}
      </main>
    </div>
  );
}
