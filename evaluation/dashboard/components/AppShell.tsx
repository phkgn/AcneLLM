"use client";

import {
  Activity,
  BarChart3,
  ClipboardCheck,
  FlaskConical,
  LayoutDashboard,
  Microscope,
  PlayCircle,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const nav = [
  {
    href: "/",
    label: "Overview",
    description: "Preflight và trạng thái",
    icon: LayoutDashboard,
  },
  {
    href: "/runs",
    label: "Run evaluations",
    description: "Khởi chạy và theo dõi",
    icon: PlayCircle,
  },
  {
    href: "/results",
    label: "Results",
    description: "Metrics và comparisons",
    icon: Activity,
  },
  {
    href: "/figures",
    label: "Figures",
    description: "Repo-wide visual analysis",
    icon: BarChart3,
  },
  {
    href: "/inspect",
    label: "Inspect samples",
    description: "Trace và output diff",
    icon: Microscope,
  },
  {
    href: "/review",
    label: "Dataset review",
    description: "Duyệt 8 bộ dữ liệu",
    icon: ClipboardCheck,
  },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-50 hidden w-[252px] flex-col border-r border-line bg-deep px-4 py-5 lg:flex">
        <Brand />
        <nav className="mt-8 space-y-1">
          {nav.map((item) => (
            <NavItem
              key={item.href}
              item={item}
              active={
                item.href === "/"
                  ? pathname === "/"
                  : pathname.startsWith(item.href)
              }
            />
          ))}
        </nav>
        <div className="mt-auto rounded-xl border border-line bg-panel/75 p-3">
          <p className="text-xs font-semibold text-ink">Local evaluation tool</p>
          <div className="mt-2 flex items-center gap-2 text-[11px] text-muted">
            <span className="h-2 w-2 rounded-full bg-moss" />
            127.0.0.1 · port 3100
          </div>
        </div>
      </aside>

      <div className="lg:pl-[252px]">
        <header className="sticky top-0 z-40 border-b border-line bg-deep/95 px-4 py-3 backdrop-blur-xl lg:hidden">
          <Brand compact />
          <nav className="mt-3 flex gap-1 overflow-x-auto pb-1">
            {nav.map((item) => {
              const Icon = item.icon;
              const active =
                item.href === "/"
                  ? pathname === "/"
                  : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold transition ${
                    active
                      ? "bg-panel text-clay shadow-sm"
                      : "text-muted hover:bg-panel/55 hover:text-ink"
                  }`}
                >
                  <Icon size={15} />
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </header>
        <main className="mx-auto max-w-[1600px] px-4 py-7 sm:px-6 lg:px-8 xl:px-10">
          {children}
        </main>
      </div>
    </div>
  );
}

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/" className="flex min-w-0 items-center gap-3">
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-clay text-white shadow-sm">
        <FlaskConical size={20} strokeWidth={1.8} />
      </span>
      <span className="min-w-0">
        <span className="font-display block truncate text-[19px] leading-tight tracking-[-0.025em]">
          AcneLLM Eval
        </span>
        <span
          className={`block truncate text-[11px] text-muted ${
            compact ? "" : "mt-0.5"
          }`}
        >
          Evaluation workspace
        </span>
      </span>
    </Link>
  );
}

function NavItem({
  item,
  active,
}: {
  item: (typeof nav)[number];
  active: boolean;
}) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      className={`flex items-start gap-3 rounded-xl px-3 py-2.5 transition ${
        active
          ? "bg-panel text-ink shadow-sm ring-1 ring-inset ring-line"
          : "text-muted hover:bg-panel/55 hover:text-ink"
      }`}
    >
      <span
        className={`mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg ${
          active ? "bg-lime text-clay" : "text-muted"
        }`}
      >
        <Icon size={16} strokeWidth={1.9} />
      </span>
      <span className="min-w-0">
        <span className={`block text-sm ${active ? "font-semibold" : "font-medium"}`}>
          {item.label}
        </span>
        <span className="mt-0.5 block truncate text-[11px] text-muted/80">
          {item.description}
        </span>
      </span>
    </Link>
  );
}
