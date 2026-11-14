// Report Center: types of /v1/reports/ and helpers shared by the page and its print layout.
import { TIME_ZONE } from "./format";

export type ReportFilter = { name: string; label: string; options: { value: string; label: string }[] };
export type ReportInfo = {
  key: string;
  title: string;
  description: string;
  icon: string;
  landscape: boolean;
  filters: ReportFilter[];
  tokens: { key: string; help: string }[];
};
export type ReportCatalog = {
  reports: ReportInfo[];
  sites: { id: number; name: string }[];
  can_combine: boolean;
  max_days: number;
  print_max_rows: number;
};

export type Kpi = { key: string; label: string; value: number | string | null; kind: "number" | "percent" | "text" };
export type Breakdown = { key: string; title: string; rows: { label: string; value: number }[] };
export type TrendPoint = { date: string } & Record<string, number | string>;
export type ReportColumn = { key: string; label: string; kind: "text" | "datetime" | "date" | "number" | "badge" };

export type ReportData = {
  report: string;
  title: string;
  description: string;
  landscape: boolean;
  sites: string[];
  period: { from: string; to: string; label: string };
  generated_at: string;
  generated_by: string;
  filters: { label: string; value: string }[];
  summary: {
    kpis: Kpi[];
    breakdowns: Breakdown[];
    trend: { series: { key: string; label: string }[]; points: TrendPoint[] };
    /** Visitor report only. */
    insights?: {
      /** Arrivals: 7 rows (Monday first) of 24 local hours. */
      heatmap: number[][];
      stay_by_purpose: { key: string; label: string; minutes: number; visits: number }[];
      purpose_trend: { series: { key: string; label: string }[]; points: TrendPoint[] };
    };
  };
  columns: ReportColumn[];
  rows: Record<string, string | number | null>[];
  count: number;
  page: number;
  page_size: number;
  truncated: boolean;
};

const number = new Intl.NumberFormat("en-SG");
const dateTime = new Intl.DateTimeFormat("en-SG", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: TIME_ZONE });
const dateOnly = new Intl.DateTimeFormat("en-SG", { day: "2-digit", month: "short", year: "numeric", timeZone: TIME_ZONE });
const shortDay = new Intl.DateTimeFormat("en-SG", { day: "numeric", month: "short", timeZone: TIME_ZONE });

export const formatKpi = (k: Kpi) =>
  k.value === null || k.value === "" ? "—" : k.kind === "percent" ? `${k.value}%` : typeof k.value === "number" ? number.format(k.value) : k.value;

export function formatCell(value: string | number | null | undefined, kind: ReportColumn["kind"]): string {
  if (value === null || value === undefined || value === "") return "—";
  if (kind === "datetime") return dateTime.format(new Date(String(value)));
  if (kind === "date") return dateOnly.format(new Date(`${value}T00:00:00+08:00`));
  if (kind === "number" && typeof value === "number") return number.format(value);
  return String(value);
}

export const dayLabel = (iso: string) => shortDay.format(new Date(`${iso}T00:00:00+08:00`));

/** Badge colour for a status cell, by its wording. */
export function badgeTone(value: string): "green" | "red" | "amber" | "blue" | "slate" {
  const v = value.toLowerCase();
  if (/(granted|approved|on site|completed|active|checked out)/.test(v) && !v.startsWith("not")) return v.includes("checked out") ? "slate" : "green";
  if (/(denied|rejected|error|blocked)/.test(v)) return "red";
  if (/(missed|not checked out|expired)/.test(v)) return "amber";
  if (/(answered|ringing)/.test(v)) return "blue";
  return "slate";
}

// --- Period presets (local Singapore dates) ---

const iso = (d: Date) => new Intl.DateTimeFormat("en-CA", { timeZone: TIME_ZONE }).format(d); // YYYY-MM-DD

function addDays(isoDate: string, days: number) {
  const d = new Date(`${isoDate}T12:00:00+08:00`);
  d.setUTCDate(d.getUTCDate() + days);
  return iso(d);
}

export const PRESETS = [
  { key: "today", label: "Today" },
  { key: "yesterday", label: "Yesterday" },
  { key: "7d", label: "Last 7 days" },
  { key: "30d", label: "Last 30 days" },
  { key: "month", label: "This month" },
  { key: "last_month", label: "Last month" },
  { key: "year", label: "This year" },
  { key: "custom", label: "Custom range" },
] as const;
export type Preset = (typeof PRESETS)[number]["key"];

export function presetRange(preset: Preset): { from: string; to: string } | null {
  const today = iso(new Date());
  const [y, m] = today.split("-");
  switch (preset) {
    case "today": return { from: today, to: today };
    case "yesterday": { const d = addDays(today, -1); return { from: d, to: d }; }
    case "7d": return { from: addDays(today, -6), to: today };
    case "30d": return { from: addDays(today, -29), to: today };
    case "month": return { from: `${y}-${m}-01`, to: today };
    case "last_month": { const end = addDays(`${y}-${m}-01`, -1); return { from: `${end.slice(0, 8)}01`, to: end }; }
    case "year": return { from: `${y}-01-01`, to: today };
    default: return null;
  }
}

/** Split a smart search into its ``key:value`` tokens and free words (same rules as the server). */
export function parseSearch(text: string): { tokens: { key: string; value: string; raw: string }[]; words: string[] } {
  const tokens: { key: string; value: string; raw: string }[] = [];
  const words: string[] = [];
  for (const match of text.matchAll(/(\w+):(?:"([^"]*)"|(\S+))|"([^"]*)"|(\S+)/g)) {
    if (match[1]) tokens.push({ key: match[1].toLowerCase(), value: match[2] ?? match[3] ?? "", raw: match[0] });
    else words.push(match[4] ?? match[5] ?? "");
  }
  return { tokens, words };
}
