import type {
  ButtonHTMLAttributes,
  HTMLAttributes,
  ReactNode,
} from "react";

export function Card({
  className = "",
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`rounded-2xl border border-line bg-panel shadow-panel ${className}`}
      {...props}
    />
  );
}

export function Button({
  className = "",
  variant = "primary",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "success" | "danger" | "ghost";
}) {
  const variants = {
    primary: "bg-clay text-white hover:bg-[#e18769]",
    secondary: "bg-lime text-ink hover:bg-[#4a3028]",
    success: "bg-[#52745a] text-white hover:bg-[#608568]",
    danger: "bg-[#a94d3e] text-white hover:bg-[#bc5a49]",
    ghost: "border border-line bg-panel text-ink hover:border-[#514c43] hover:bg-sand/70",
  };
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-[10px] px-4 py-2.5 text-sm font-semibold shadow-sm transition disabled:cursor-not-allowed disabled:opacity-45 ${variants[variant]} ${className}`}
      {...props}
    />
  );
}

export function Pill({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "good" | "bad" | "warn" | "neutral" | "info";
}) {
  const tones = {
    good: "bg-[#1e2b22] text-[#8fbc98] ring-[#304536]",
    bad: "bg-[#321e1a] text-[#ef8e78] ring-[#523029]",
    warn: "bg-[#332719] text-[#e8b96d] ring-[#514027]",
    neutral: "bg-sand text-ink/65 ring-line",
    info: "bg-[#1d2b31] text-[#83b8cf] ring-[#2d424b]",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold tracking-[0.01em] ring-1 ring-inset ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-7 flex flex-col justify-between gap-5 border-b border-line/80 pb-6 lg:flex-row lg:items-end">
      <div className="max-w-3xl">
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-clay">
          {eyebrow}
        </p>
        <h1 className="font-display text-4xl font-normal leading-[1.08] tracking-[-0.035em] sm:text-[46px]">
          {title}
        </h1>
        <p className="mt-3 max-w-2xl text-[15px] leading-6 text-muted">
          {description}
        </p>
      </div>
      {actions}
    </div>
  );
}

export function EmptyState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-xl border border-dashed border-line bg-sand/35 px-6 py-10 text-center">
      <p className="font-display text-xl">{title}</p>
      <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-muted">
        {description}
      </p>
    </div>
  );
}

export const inputClass =
  "w-full rounded-[10px] border border-line bg-[#211f1b] px-3 py-2.5 text-sm font-normal text-ink shadow-sm outline-none transition placeholder:text-muted/55 hover:border-[#514c43] focus:border-clay focus:ring-4 focus:ring-clay/15";

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const totalSeconds = Math.round(ms / 1000);
  if (totalSeconds < 60) return `${totalSeconds}s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes < 60) return `${minutes}m ${seconds}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

export function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

export function formatMetric(value: unknown, percent = true): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  if (percent && Math.abs(value) <= 1) return `${(value * 100).toFixed(1)}%`;
  return Number.isInteger(value) ? String(value) : value.toFixed(3);
}
