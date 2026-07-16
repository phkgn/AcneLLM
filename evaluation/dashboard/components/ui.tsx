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
      className={`rounded-[24px] border border-line bg-panel shadow-panel ${className}`}
      {...props}
    />
  );
}

export function Button({
  className = "",
  variant = "primary",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost";
}) {
  const variants = {
    primary: "bg-ink text-white hover:bg-moss",
    secondary: "bg-lime text-ink hover:bg-[#bdd957]",
    danger: "bg-ember text-white hover:bg-[#923d29]",
    ghost: "border border-line bg-panel text-ink hover:bg-canvas",
  };
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-black transition disabled:cursor-not-allowed disabled:opacity-45 ${variants[variant]} ${className}`}
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
    good: "bg-moss/10 text-moss ring-moss/15",
    bad: "bg-ember/10 text-ember ring-ember/15",
    warn: "bg-amber-100 text-amber-800 ring-amber-200",
    neutral: "bg-ink/5 text-ink/60 ring-ink/10",
    info: "bg-blue-50 text-blue-700 ring-blue-100",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-black uppercase tracking-[0.08em] ring-1 ring-inset ${tones[tone]}`}
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
    <div className="mb-7 flex flex-col justify-between gap-5 lg:flex-row lg:items-end">
      <div className="max-w-3xl">
        <p className="mb-2 text-xs font-black uppercase tracking-[0.2em] text-moss">
          {eyebrow}
        </p>
        <h1 className="text-3xl font-black tracking-[-0.04em] sm:text-4xl">
          {title}
        </h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-ink/58">
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
    <div className="rounded-2xl border border-dashed border-line bg-canvas/50 px-6 py-10 text-center">
      <p className="font-black">{title}</p>
      <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-ink/50">
        {description}
      </p>
    </div>
  );
}

export const inputClass =
  "w-full rounded-xl border border-line bg-white px-3 py-2.5 text-sm font-semibold text-ink shadow-sm outline-none transition placeholder:text-ink/30 focus:border-moss focus:ring-4 focus:ring-moss/10";

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
