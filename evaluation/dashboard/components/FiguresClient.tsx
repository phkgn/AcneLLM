"use client";

import {
  AlertTriangle,
  Download,
  ExternalLink,
  ImageIcon,
  LoaderCircle,
  Play,
  RefreshCw,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ErrorBar,
  Legend,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import {
  FIGURE_GROUPS,
  figureArtifactPath,
  parseFigureManifest,
  type FigureGroup,
  type FigureGroupId,
  type FigureManifest,
  type FigureManifestEntry,
} from "@/lib/figures";
import type { CommandId, JobRecord } from "@/lib/types";
import {
  Button,
  Card,
  EmptyState,
  PageHeader,
  Pill,
} from "./ui";

type ChartSeries = {
  key: string;
  label?: string;
  stack?: string;
  error_key?: string;
};

type ChartPayload = {
  id?: string;
  title?: string;
  chart_type?: string;
  data?: Array<Record<string, unknown>>;
  series?: ChartSeries[];
  x_key?: string;
  x_data_key?: string;
  y_data_key?: string;
  size_key?: string;
  group_key?: string;
  x_label?: string;
  y_label?: string;
  rows?: string[];
  columns?: string[];
  cells?: Array<{
    row?: string;
    column?: string;
    value?: number;
    n?: number;
  }>;
  value_label?: string;
  domain?: [number, number] | {
    x?: [number, number];
    y?: [number, number];
  };
  threshold?: number;
  threshold_label?: string;
  annotation?: string;
  highlight_region?: {
    x_max?: number;
    y_min?: number;
    label?: string;
  };
};

const palette = ["#d97757", "#78a681", "#83b8cf", "#e8b96d", "#b79bd1", "#ef8e78"];
const tooltipStyle = {
  background: "#1c1b18",
  border: "1px solid #37342e",
  borderRadius: 10,
  color: "#eeeae3",
  fontSize: 12,
};

async function fetchTextFile(path: string): Promise<string> {
  const response = await fetch(
    `/api/files?path=${encodeURIComponent(path)}`,
    { cache: "no-store" },
  );
  const body = (await response.json()) as {
    content?: string;
    error?: string;
  };
  if (!response.ok || typeof body.content !== "string") {
    throw new Error(body.error ?? `Không đọc được ${path}.`);
  }
  return body.content;
}

function formatGeneratedAt(value: string | null | undefined): string {
  if (!value) return "Chưa generate";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("vi-VN");
}

function commandArgs(commandId: CommandId, pdf = false) {
  if (commandId === "figures_kb" || commandId === "figures_all") {
    return { sample: 8_000, pdf };
  }
  return { pdf };
}

export function FiguresClient() {
  const [activeId, setActiveId] = useState<FigureGroupId>("kb");
  const [manifest, setManifest] = useState<FigureManifest | null>(null);
  const [charts, setCharts] = useState<Record<string, ChartPayload>>({});
  const [chartErrors, setChartErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const activeGroup = FIGURE_GROUPS.find((group) => group.id === activeId)!;

  const loadManifest = useCallback(async (group: FigureGroup) => {
    if (!group.manifestPath) {
      setManifest(null);
      setCharts({});
      setChartErrors({});
      setError(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const text = await fetchTextFile(group.manifestPath);
      const nextManifest = parseFigureManifest(JSON.parse(text));
      const chartEntries = nextManifest.figures.filter(
        (figure) =>
          figure.status === "ok" &&
          figure.kind === "chart" &&
          typeof figure.file === "string",
      );
      const loadedCharts: Record<string, ChartPayload> = {};
      const errors: Record<string, string> = {};
      await Promise.all(
        chartEntries.map(async (figure) => {
          try {
            const chartText = await fetchTextFile(
              figureArtifactPath(group.id, figure.file!),
            );
            loadedCharts[figure.id] = JSON.parse(chartText) as ChartPayload;
          } catch (chartError) {
            errors[figure.id] = (chartError as Error).message;
          }
        }),
      );
      setManifest(nextManifest);
      setCharts(loadedCharts);
      setChartErrors(errors);
      setError(null);
    } catch (loadError) {
      setManifest(null);
      setCharts({});
      setChartErrors({});
      setError((loadError as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshJobs = useCallback(async () => {
    try {
      const response = await fetch("/api/jobs", { cache: "no-store" });
      const body = (await response.json()) as { jobs?: JobRecord[] };
      if (response.ok && Array.isArray(body.jobs)) setJobs(body.jobs);
    } catch {
      // Manifest rendering remains usable when the jobs registry is unavailable.
    }
  }, []);

  useEffect(() => {
    void loadManifest(activeGroup);
  }, [activeGroup, loadManifest]);

  useEffect(() => {
    void refreshJobs();
    const timer = window.setInterval(() => void refreshJobs(), 2_000);
    return () => window.clearInterval(timer);
  }, [refreshJobs]);

  useEffect(() => {
    if (!activeGroup.manifestPath) return;
    const source = new EventSource(
      `/api/files/watch?path=${encodeURIComponent(activeGroup.manifestPath)}`,
    );
    const reload = () => void loadManifest(activeGroup);
    source.addEventListener("chunk", reload);
    source.addEventListener("reset", reload);
    return () => source.close();
  }, [activeGroup, loadManifest]);

  const runningCommands = useMemo(
    () =>
      new Set(
        jobs
          .filter((job) => ["running", "stopping"].includes(job.status))
          .map((job) => job.commandId),
      ),
    [jobs],
  );

  async function startCommand(commandId: CommandId, pdf = false) {
    const key = `${commandId}:${pdf ? "pdf" : "normal"}`;
    setBusy(key);
    try {
      const response = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          commandId,
          args: commandArgs(commandId, pdf),
        }),
      });
      const body = (await response.json()) as {
        job?: JobRecord;
        error?: string;
      };
      if (!response.ok || !body.job) {
        throw new Error(body.error ?? "Không thể tạo figure job.");
      }
      setJobs((current) => [body.job!, ...current]);
      setError(null);
    } catch (startError) {
      setError((startError as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function exportAll() {
    setBusy("export");
    try {
      const commandId: CommandId = "figures_all";
      const response = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          commandId,
          args: commandArgs(commandId, true),
        }),
      });
      const body = (await response.json()) as {
        job?: JobRecord;
        error?: string;
      };
      if (!response.ok || !body.job) {
        throw new Error(body.error ?? "Không thể generate fresh snapshot.");
      }
      setJobs((current) => [body.job!, ...current]);
      setError(null);
    } catch (exportError) {
      setError((exportError as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const okCount =
    manifest?.figures.filter((figure) => figure.status === "ok").length ?? 0;
  const skippedCount =
    manifest?.figures.filter((figure) => figure.status === "skipped").length ?? 0;
  const groupRunning =
    runningCommands.has("figures_all") ||
    (
      activeGroup.commandId !== null &&
      runningCommands.has(activeGroup.commandId)
    );

  return (
    <div>
      <PageHeader
        eyebrow="Repository figures"
        title="Visualize the full evaluation system"
        description="Python recomputes a fresh snapshot from current repository data. Previous figure artifacts are never used as generator input."
        actions={
          <Button
            variant="secondary"
            onClick={() => void exportAll()}
            disabled={
              busy === "export" ||
              ["figures_all", "figures_eval", "figures_kb", "figures_usage"].some((command) =>
                runningCommands.has(command as CommandId),
              )
            }
          >
            {busy === "export" ? (
              <LoaderCircle size={16} className="animate-spin" />
            ) : (
              <Download size={16} />
            )}
            Generate all fresh PNG+PDF
          </Button>
        }
      />

      <div className="mb-5 flex flex-wrap gap-2" role="tablist" aria-label="Figure groups">
        {FIGURE_GROUPS.map((group) => (
          <button
            key={group.id}
            type="button"
            role="tab"
            aria-selected={activeId === group.id}
            onClick={() => setActiveId(group.id)}
            className={`rounded-xl border px-3.5 py-2.5 text-left text-sm font-semibold transition ${
              activeId === group.id
                ? "border-clay bg-clay text-white"
                : "border-line bg-panel text-muted hover:border-[#514c43] hover:text-ink"
            }`}
          >
            <span className="mr-2 opacity-70">{group.shortLabel}</span>
            {group.label}
          </button>
        ))}
      </div>

      {activeId !== "diagrams" ? (
        <Card className="mb-5 flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone={okCount ? "good" : "neutral"}>{okCount} ready</Pill>
            <Pill tone={skippedCount ? "warn" : "neutral"}>
              {skippedCount} skipped
            </Pill>
            {groupRunning ? (
              <Pill tone="info">Generator running</Pill>
            ) : null}
            <span className="text-xs text-muted">
              Generated {formatGeneratedAt(manifest?.generated_at)}
            </span>
            {manifest?.generation_id ? (
              <span
                className="text-xs text-muted"
                title={manifest.generation_id}
              >
                Snapshot {manifest.generation_id.slice(-10)}
              </span>
            ) : null}
          </div>
          {activeGroup.commandId ? (
            <Button
              variant="ghost"
              onClick={() => void startCommand(activeGroup.commandId!)}
              disabled={
                groupRunning ||
                busy === `${activeGroup.commandId}:normal`
              }
            >
              {groupRunning ||
              busy === `${activeGroup.commandId}:normal` ? (
                <LoaderCircle size={15} className="animate-spin" />
              ) : (
                <RefreshCw size={15} />
              )}
              Regenerate group
            </Button>
          ) : null}
        </Card>
      ) : null}

      {error ? (
        <div className="mb-5 flex items-start gap-3 rounded-xl border border-[#523029] bg-[#321e1a] px-4 py-3 text-sm text-[#efaa99]">
          <AlertTriangle size={17} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      ) : null}

      {activeId === "diagrams" ? (
        <DiagramsTab />
      ) : loading ? (
        <Card className="grid min-h-64 place-items-center p-8">
          <div className="flex items-center gap-3 text-sm text-muted">
            <LoaderCircle size={18} className="animate-spin" />
            Loading figure artifacts…
          </div>
        </Card>
      ) : manifest ? (
        <div className="grid gap-5 xl:grid-cols-2">
          {manifest.figures.map((figure) => (
            <FigureCard
              key={figure.id}
              group={activeGroup}
              figure={figure}
              chart={charts[figure.id]}
              chartError={chartErrors[figure.id]}
              running={groupRunning}
              busy={busy === `${activeGroup.commandId}:normal`}
              onRegenerate={
                activeGroup.commandId
                  ? () => void startCommand(activeGroup.commandId!)
                  : undefined
              }
            />
          ))}
        </div>
      ) : (
        <Card className="p-5">
          <EmptyState
            title="No manifest yet"
            description="Run the group generator to create its manifest and figure artifacts."
          />
        </Card>
      )}
    </div>
  );
}

function FigureCard({
  group,
  figure,
  chart,
  chartError,
  running,
  busy,
  onRegenerate,
}: {
  group: FigureGroup;
  figure: FigureManifestEntry;
  chart?: ChartPayload;
  chartError?: string;
  running: boolean;
  busy: boolean;
  onRegenerate?: () => void;
}) {
  const skipped = figure.status === "skipped";
  return (
    <Card
      className={`overflow-hidden ${
        skipped ? "border-line/70 bg-[#191816]" : ""
      }`}
    >
      <div className="flex flex-col gap-3 border-b border-line px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone={skipped ? "neutral" : "good"}>{figure.id}</Pill>
            {skipped ? <Pill tone="warn">Skipped</Pill> : null}
          </div>
          <h2 className="font-display mt-3 text-2xl leading-tight">
            {figure.title}
          </h2>
          <p className="mt-2 text-sm leading-6 text-muted">{figure.caption}</p>
        </div>
        <div className="flex shrink-0 gap-2">
          {figure.pdf_file ? (
            <a
              href={`/api/files?path=${encodeURIComponent(
                figureArtifactPath(group.id, figure.pdf_file),
              )}&raw=1`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-[10px] border border-line bg-panel px-3 py-2 text-xs font-semibold text-ink transition hover:border-[#514c43]"
            >
              <Download size={14} />
              PDF
            </a>
          ) : null}
          {onRegenerate ? (
            <button
              type="button"
              onClick={onRegenerate}
              disabled={running || busy}
              className="inline-flex items-center gap-2 rounded-[10px] border border-line bg-panel px-3 py-2 text-xs font-semibold text-ink transition hover:border-[#514c43] disabled:cursor-not-allowed disabled:opacity-45"
            >
              {running || busy ? (
                <LoaderCircle size={14} className="animate-spin" />
              ) : (
                <Play size={14} />
              )}
              Regenerate
            </button>
          ) : null}
        </div>
      </div>

      <div className="p-5">
        {skipped ? (
          <div className="grid min-h-72 place-items-center rounded-xl border border-dashed border-line bg-sand/25 p-8 text-center">
            <div>
              <AlertTriangle size={24} className="mx-auto text-muted" />
              <p className="mt-3 text-sm font-semibold text-ink">
                Figure was skipped gracefully
              </p>
              <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-muted">
                {figure.skip_reason ?? "No skip reason was recorded."}
              </p>
            </div>
          </div>
        ) : figure.kind === "png" && figure.file ? (
          <div className="grid min-h-72 place-items-center overflow-hidden rounded-xl bg-sand/25">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`/api/files?path=${encodeURIComponent(
                figureArtifactPath(group.id, figure.file),
              )}&raw=1`}
              alt={figure.title}
              className="max-h-[620px] w-full object-contain"
            />
          </div>
        ) : chartError ? (
          <div className="grid min-h-72 place-items-center rounded-xl border border-dashed border-[#523029] bg-[#321e1a] p-8 text-center text-sm text-[#efaa99]">
            {chartError}
          </div>
        ) : chart ? (
          <FigureChart payload={chart} />
        ) : (
          <div className="grid min-h-72 place-items-center text-sm text-muted">
            <ImageIcon size={20} />
          </div>
        )}
      </div>

      <div className="border-t border-line px-5 py-3 text-xs text-muted">
        Source: <code className="text-ink/80">{figure.source_data}</code>
      </div>
    </Card>
  );
}

function FigureChart({ payload }: { payload: ChartPayload }) {
  const type = payload.chart_type ?? "bar";
  if (type === "heatmap") return <Heatmap payload={payload} />;
  if (type === "scatter") return <ScatterPlot payload={payload} />;
  if (type === "line") return <LinePlot payload={payload} />;
  return <BarPlot payload={payload} />;
}

function BarPlot({ payload }: { payload: ChartPayload }) {
  const data = payload.data ?? [];
  const series = payload.series ?? [];
  const thresholdAxis =
    typeof payload.threshold === "number" &&
    data.some((row) => typeof row.bin_start === "number");
  const xKey = thresholdAxis ? "bin_start" : payload.x_key ?? "label";
  const domain = Array.isArray(payload.domain)
    ? payload.domain
    : ["auto", "auto"];
  return (
    <div>
      {payload.threshold_label ? (
        <p className="mb-2 text-xs text-muted">{payload.threshold_label}</p>
      ) : null}
      <div className="h-[350px] w-full" role="img" aria-label={payload.title}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 12, right: 14, left: 4, bottom: 72 }}>
            <CartesianGrid stroke="#37342e" vertical={false} />
            <XAxis
              dataKey={xKey}
              type={thresholdAxis ? "number" : "category"}
              tick={{ fill: "#a8a198", fontSize: 11 }}
              tickFormatter={(value) => {
                const text = String(value);
                return text.length > 18 ? `${text.slice(0, 17)}…` : text;
              }}
              angle={thresholdAxis ? 0 : -32}
              textAnchor={thresholdAxis ? "middle" : "end"}
              height={78}
              label={{
                value: payload.x_label,
                position: "insideBottom",
                offset: -58,
                fill: "#a8a198",
              }}
            />
            <YAxis
              domain={domain}
              tick={{ fill: "#a8a198", fontSize: 11 }}
              label={{
                value: payload.y_label,
                angle: -90,
                position: "insideLeft",
                fill: "#a8a198",
              }}
            />
            <Tooltip contentStyle={tooltipStyle} />
            {series.length > 1 ? <Legend wrapperStyle={{ fontSize: 11 }} /> : null}
            {typeof payload.threshold === "number" && thresholdAxis ? (
              <ReferenceLine
                x={payload.threshold}
                stroke="#e8b96d"
                strokeDasharray="5 4"
                label={{
                  value: "threshold",
                  fill: "#e8b96d",
                  fontSize: 11,
                }}
              />
            ) : null}
            {series.map((item, index) => (
              <Bar
                key={item.key}
                dataKey={item.key}
                name={item.label ?? item.key}
                stackId={item.stack}
                fill={palette[index % palette.length]}
                radius={item.stack ? 0 : [4, 4, 0, 0]}
              >
                {item.error_key ? (
                  <ErrorBar
                    dataKey={item.error_key}
                    direction="y"
                    width={4}
                    stroke="#eeeae3"
                  />
                ) : null}
              </Bar>
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function LinePlot({ payload }: { payload: ChartPayload }) {
  const data = payload.data ?? [];
  const series = payload.series ?? [];
  const domain = Array.isArray(payload.domain)
    ? payload.domain
    : ["auto", "auto"];
  return (
    <div>
      {payload.annotation ? (
        <p className="mb-2 text-xs text-muted">{payload.annotation}</p>
      ) : null}
      <div className="h-[350px] w-full" role="img" aria-label={payload.title}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 12, right: 18, left: 4, bottom: 44 }}>
            <CartesianGrid stroke="#37342e" vertical={false} />
            <XAxis
              dataKey={payload.x_key ?? "x"}
              tick={{ fill: "#a8a198", fontSize: 11 }}
              label={{
                value: payload.x_label,
                position: "insideBottom",
                offset: -26,
                fill: "#a8a198",
              }}
            />
            <YAxis
              domain={domain}
              tick={{ fill: "#a8a198", fontSize: 11 }}
              label={{
                value: payload.y_label,
                angle: -90,
                position: "insideLeft",
                fill: "#a8a198",
              }}
            />
            <Tooltip contentStyle={tooltipStyle} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            {series.map((item, index) => (
              <Line
                key={item.key}
                type="monotone"
                dataKey={item.key}
                name={item.label ?? item.key}
                stroke={palette[index % palette.length]}
                strokeWidth={2}
                dot={{ r: 3 }}
                connectNulls
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function ScatterPlot({ payload }: { payload: ChartPayload }) {
  const xKey = payload.x_data_key ?? "x";
  const yKey = payload.y_data_key ?? "y";
  const groupKey = payload.group_key;
  const groups = useMemo(() => {
    const data = payload.data ?? [];
    const grouped = new Map<string, Array<Record<string, unknown>>>();
    for (const row of data) {
      const group = groupKey ? String(row[groupKey] ?? "data") : "data";
      const current = grouped.get(group) ?? [];
      current.push(row);
      grouped.set(group, current);
    }
    return [...grouped.entries()];
  }, [payload.data, groupKey]);
  const domain =
    payload.domain && !Array.isArray(payload.domain) ? payload.domain : {};
  return (
    <div>
      {payload.annotation ? (
        <p className="mb-2 text-xs text-muted">{payload.annotation}</p>
      ) : null}
      <div className="h-[350px] w-full" role="img" aria-label={payload.title}>
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 12, right: 18, left: 4, bottom: 44 }}>
            <CartesianGrid stroke="#37342e" />
            <XAxis
              type="number"
              dataKey={xKey}
              name={payload.x_label ?? xKey}
              domain={domain.x ?? ["auto", "auto"]}
              tick={{ fill: "#a8a198", fontSize: 11 }}
              label={{
                value: payload.x_label,
                position: "insideBottom",
                offset: -26,
                fill: "#a8a198",
              }}
            />
            <YAxis
              type="number"
              dataKey={yKey}
              name={payload.y_label ?? yKey}
              domain={domain.y ?? ["auto", "auto"]}
              tick={{ fill: "#a8a198", fontSize: 11 }}
              label={{
                value: payload.y_label,
                angle: -90,
                position: "insideLeft",
                fill: "#a8a198",
              }}
            />
            {payload.size_key ? (
              <ZAxis dataKey={payload.size_key} range={[30, 250]} />
            ) : null}
            <Tooltip
              cursor={{ strokeDasharray: "4 4" }}
              contentStyle={tooltipStyle}
            />
            {groups.length > 1 ? <Legend wrapperStyle={{ fontSize: 11 }} /> : null}
            {payload.highlight_region ? (
              <ReferenceArea
                x1={domain.x?.[0] ?? 0}
                x2={payload.highlight_region.x_max}
                y1={payload.highlight_region.y_min}
                y2={domain.y?.[1] ?? 5}
                fill="#e27760"
                fillOpacity={0.12}
                stroke="#e27760"
                strokeDasharray="4 4"
                label={{
                  value: payload.highlight_region.label,
                  fill: "#e8b96d",
                  fontSize: 10,
                }}
              />
            ) : null}
            {groups.map(([group, points], index) => (
              <Scatter
                key={group}
                name={group}
                data={points}
                fill={palette[index % palette.length]}
                fillOpacity={0.68}
              />
            ))}
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function Heatmap({ payload }: { payload: ChartPayload }) {
  const rows = payload.rows ?? [];
  const columns = payload.columns ?? [];
  const cells = payload.cells ?? [];
  const lookup = new Map(
    cells.map((cell) => [
      `${cell.row}\u0000${cell.column}`,
      cell,
    ]),
  );
  const max = Math.max(1, ...cells.map((cell) => Number(cell.value ?? 0)));
  const minWidth = Math.max(560, 150 + columns.length * 84);
  return (
    <div className="overflow-x-auto pb-2">
      <div
        role="table"
        aria-label={payload.title}
        className="grid gap-1 text-xs"
        style={{
          minWidth,
          gridTemplateColumns: `140px repeat(${columns.length}, minmax(76px, 1fr))`,
        }}
      >
        <div className="sticky left-0 z-10 bg-panel p-2 font-semibold text-muted">
          {payload.value_label ?? "Value"}
        </div>
        {columns.map((column) => (
          <div
            key={column}
            role="columnheader"
            className="grid min-h-16 place-items-end break-words p-2 text-center font-semibold text-muted"
          >
            {column}
          </div>
        ))}
        {rows.map((row) => (
          <HeatmapRow
            key={row}
            row={row}
            columns={columns}
            lookup={lookup}
            max={max}
          />
        ))}
      </div>
    </div>
  );
}

function HeatmapRow({
  row,
  columns,
  lookup,
  max,
}: {
  row: string;
  columns: string[];
  lookup: Map<string, { value?: number; n?: number }>;
  max: number;
}) {
  return (
    <>
      <div
        role="rowheader"
        className="sticky left-0 z-10 flex items-center bg-panel p-2 font-semibold text-ink"
      >
        {row}
      </div>
      {columns.map((column) => {
        const cell = lookup.get(`${row}\u0000${column}`);
        const value = Number(cell?.value ?? 0);
        const alpha = value <= 0 ? 0.04 : 0.16 + 0.72 * Math.sqrt(value / max);
        return (
          <div
            key={column}
            role="cell"
            aria-label={`${row}, ${column}: ${value}${
              cell?.n ? `, n=${cell.n}` : ""
            }`}
            className="grid min-h-12 place-items-center rounded-md p-1 font-semibold text-ink"
            style={{ background: `rgba(217, 119, 87, ${alpha})` }}
          >
            {Number.isInteger(value) ? value : value.toFixed(2)}
          </div>
        );
      })}
    </>
  );
}

function DiagramsTab() {
  return (
    <div className="space-y-5">
      <div className="grid gap-5 xl:grid-cols-2">
        <Card className="overflow-hidden">
          <div className="border-b border-line px-5 py-4">
            <Pill tone="info">E2</Pill>
            <h2 className="font-display mt-3 text-2xl">Production chat pipeline</h2>
            <p className="mt-2 text-sm leading-6 text-muted">
              Intake tasks, intent fork, RAG/LLM paths and final safety/persistence.
            </p>
          </div>
          <div className="overflow-x-auto p-5">
            <MermaidDiagram definition={pipelineDiagram} id="pipeline-diagram" />
          </div>
        </Card>
        <Card className="overflow-hidden">
          <div className="border-b border-line px-5 py-4">
            <Pill tone="info">E3</Pill>
            <h2 className="font-display mt-3 text-2xl">Evaluation architecture</h2>
            <p className="mt-2 text-sm leading-6 text-muted">
              Four evaluation tiers applied across the S0–S4 system matrix.
            </p>
          </div>
          <div className="overflow-x-auto p-5">
            <MermaidDiagram definition={evaluationDiagram} id="evaluation-diagram" />
          </div>
        </Card>
      </div>
      <Card className="flex flex-col gap-3 p-5 sm:flex-row">
        <a
          href="/api/files?path=acnellm_pipeline.html&raw=1"
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center justify-center gap-2 rounded-[10px] bg-clay px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#e18769]"
        >
          <ExternalLink size={15} />
          Open AcneLLM pipeline
        </a>
        <a
          href="/api/files?path=pipeline_simulator.html&raw=1"
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center justify-center gap-2 rounded-[10px] border border-line bg-panel px-4 py-2.5 text-sm font-semibold text-ink transition hover:border-[#514c43]"
        >
          <ExternalLink size={15} />
          Open pipeline simulator
        </a>
      </Card>
    </div>
  );
}

function MermaidDiagram({
  definition,
  id,
}: {
  definition: string;
  id: string;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function render() {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: "dark",
          themeVariables: {
            background: "#1c1b18",
            primaryColor: "#3b2822",
            primaryTextColor: "#eeeae3",
            primaryBorderColor: "#d97757",
            lineColor: "#a8a198",
            secondaryColor: "#25231f",
            tertiaryColor: "#1d2b31",
            fontFamily: "Segoe UI, sans-serif",
          },
        });
        const result = await mermaid.render(`${id}-${Date.now()}`, definition);
        if (!cancelled && container.current) {
          container.current.innerHTML = result.svg;
          setError(null);
        }
      } catch (renderError) {
        if (!cancelled) setError((renderError as Error).message);
      }
    }
    void render();
    return () => {
      cancelled = true;
    };
  }, [definition, id]);

  if (error) {
    return (
      <div className="rounded-xl border border-[#523029] bg-[#321e1a] p-4 text-sm text-[#efaa99]">
        {error}
      </div>
    );
  }
  return (
    <div
      ref={container}
      className="min-h-[420px] min-w-[680px] [&_svg]:h-auto [&_svg]:w-full"
      aria-label={id}
    />
  );
}

const pipelineDiagram = String.raw`
flowchart TD
  U["User message via SSE"] --> P["1. prepare_user_text"]
  P --> N["2. normalize_chat_message"]
  N --> G["3. guardrails.pre_check"]
  G --> R["4. route_intent: intent x subject"]
  R -->|advise + self| H["5a. fold history + completeness + planner"]
  H --> RET["6a. Hybrid retrieve: dense + BM25 + RRF + rerank"]
  RET --> AP["7a. stream_user prompt + LLM stream"]
  R -->|knowledge| KR["5b. retrieve + knowledge prompt"]
  KR --> AP
  R -->|clarify| CL["5c. clarify prompt; no retrieval"]
  CL --> AP
  R -->|reject| RJ["5d. immediate refusal; no LLM"]
  AP --> S["8. safety suffix + SSE + session + audit"]
  RJ --> S
`;

const evaluationDiagram = String.raw`
flowchart LR
  subgraph T["Evaluation tiers"]
    T1["T1: module unit tests"]
    T2["T2: retrieval"]
    T3["T3: controlled generation"]
    T4["T4: end-to-end SSE"]
    T1 --> T2 --> T3 --> T4
  end
  subgraph M["System matrix"]
    S0["S0 Base only"]
    S1["S1 Finetuned only"]
    S2["S2 Base + RAG"]
    S3["S3 Finetuned + RAG"]
    S4["S4 Extractive RAG"]
  end
  T1 -.-> S0
  T2 -.-> S2
  T2 -.-> S3
  T2 -.-> S4
  T3 -.-> S0
  T3 -.-> S1
  T3 -.-> S2
  T3 -.-> S3
  T3 -.-> S4
  T4 -.-> S0
  T4 -.-> S1
  T4 -.-> S2
  T4 -.-> S3
`;
