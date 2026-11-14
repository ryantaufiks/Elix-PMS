"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";

import { BarList, DailyChart, Heatmap } from "@/components/charts";
import { Tabs } from "@/components/forms";
import { Icon } from "@/components/icons";
import { upsellText, useModule, useModuleCatalogue } from "@/components/ModuleGate";
import { ReportPrint } from "@/components/ReportPrint";
import {
  Badge, Button, Card, CardHeader, cx, Empty, ErrorNote, Field, Input, Loading, PageHeader, Pagination, Select, Table, Td, Th, useToast,
} from "@/components/ui";
import { api, ApiError, query } from "@/lib/api";
import { formatDate } from "@/lib/format";
import {
  badgeTone, dayLabel, formatCell, formatKpi, parseSearch, type Preset, PRESETS, presetRange, type ReportCatalog, type ReportData,
} from "@/lib/reports";
import { useSession } from "@/lib/session";

const PAGE_SIZE = 50;
const REPORT_KEY = "elix.report";
const FILTERS_KEY = "elix.reportFilters";  // "open" keeps the filter panel open in this browser.

function useDebounced<T>(value: T, ms = 400) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return debounced;
}

/** Superusers pick any number of sites; everyone else reports on one of their own. */
function SitePicker({ catalog, value, onChange }: { catalog: ReportCatalog; value: number[] | "all"; onChange: (v: number[] | "all") => void }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    window.addEventListener("pointerdown", close);
    return () => window.removeEventListener("pointerdown", close);
  }, [open]);

  if (!catalog.can_combine) {
    return (
      <Select value={value === "all" ? "" : value[0]} onChange={(e) => onChange([Number(e.target.value)])} disabled={catalog.sites.length < 2}>
        {catalog.sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </Select>
    );
  }
  const selected = value === "all" ? catalog.sites.map((s) => s.id) : value;
  const label = value === "all" ? `All sites (${catalog.sites.length})`
    : selected.length === 1 ? catalog.sites.find((s) => s.id === selected[0])?.name ?? "1 site" : `${selected.length} sites`;
  const toggle = (id: number) => {
    const next = selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id];
    if (next.length) onChange(next.length === catalog.sites.length ? "all" : next);
  };
  return (
    <div ref={box} className="relative">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className="flex h-10 w-full items-center justify-between gap-2 rounded-md border border-line bg-surface px-3 text-left text-sm text-ink hover:bg-surface-2">
        <span className="truncate">{label}</span><Icon name="chevron" className="h-4 w-4 rotate-90 text-muted" />
      </button>
      {open && (
        <div className="absolute z-30 mt-1 max-h-72 w-full min-w-60 overflow-y-auto rounded-lg border border-line bg-surface p-1.5 shadow-card">
          <label className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium text-ink hover:bg-surface-2">
            <input type="checkbox" checked={value === "all"} onChange={() => onChange(value === "all" ? [catalog.sites[0].id] : "all")} className="h-4 w-4" />
            All sites (consolidated)
          </label>
          <div className="my-1 border-t border-line" />
          {catalog.sites.map((s) => (
            <label key={s.id} className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm text-body hover:bg-surface-2">
              <input type="checkbox" checked={selected.includes(s.id)} onChange={() => toggle(s.id)} className="h-4 w-4" />
              {s.name}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

/** Short tab labels; the full title still heads the printout. */
const TAB_LABEL: Record<string, string> = {
  summary: "Summary", visits: "Visitors", access: "Access", vehicles: "Vehicles", intercom: "Intercom", invitations: "Invitations",
};

export default function ReportsPage() {
  const { condo } = useSession();
  const advanced = useModule("advanced_reports");
  const advancedInfo = useModuleCatalogue()?.modules.find((x) => x.key === "advanced_reports");
  const toast = useToast();
  const { data: catalog, error: catalogError } = useSWR<ReportCatalog>("/v1/reports/");
  const [reportKey, setReportKey] = useState("visits");
  const [sites, setSites] = useState<number[] | "all">([condo.id]);
  const [preset, setPreset] = useState<Preset>("7d");
  const [range, setRange] = useState(() => presetRange("7d")!);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState<"" | "print" | "csv" | "xlsx">("");
  const [printData, setPrintData] = useState<ReportData | null>(null);
  const [panel, setPanel] = useState(false);
  const searchBox = useRef<HTMLInputElement>(null);
  const q = useDebounced(search);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(REPORT_KEY);
      if (saved) setReportKey(saved);
      setPanel(localStorage.getItem(FILTERS_KEY) === "open");
    } catch {}
  }, []);
  const togglePanel = (open = !panel) => {
    setPanel(open);
    try { localStorage.setItem(FILTERS_KEY, open ? "open" : "closed"); } catch {}
  };
  useEffect(() => setSites([condo.id]), [condo.id]);

  const report = catalog?.reports.find((r) => r.key === reportKey) ?? catalog?.reports[0];
  const params = useMemo(() => ({
    condominium: sites === "all" ? "all" : sites.join(","),
    date_from: range.from, date_to: range.to, q: q.trim(),
    ...Object.fromEntries((report?.filters ?? []).map((f) => [f.name, filters[f.name] ?? ""])),
  }), [sites, range, q, filters, report]);
  useEffect(() => setPage(1), [params]);

  const path = report ? `/v1/reports/${report.key}/` : null;
  const { data, error, isLoading } = useSWR<ReportData>(path ? `${path}${query({ ...params, page, page_size: PAGE_SIZE })}` : null, { keepPreviousData: true });

  function choose(key: string) {
    setReportKey(key);
    setFilters({});
    setSearch("");
    try { localStorage.setItem(REPORT_KEY, key); } catch {}
  }

  function pickPreset(p: Preset) {
    setPreset(p);
    const r = presetRange(p);
    if (r) setRange(r);
    else togglePanel(true);  // Custom range: show the From / To dates.
  }

  async function download(kind: "csv" | "xlsx") {
    if (!path) return;
    setBusy(kind);
    try {
      const response = await api<Response>(`${path}${query({ ...params, export: kind })}`, { raw: true });
      const name = /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") ?? "")?.[1] ?? `report.${kind}`;
      const url = URL.createObjectURL(await response.blob());
      const a = Object.assign(document.createElement("a"), { href: url, download: name });
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch (err) {
      toast("error", err instanceof ApiError ? err.message : "Export failed.");
    } finally {
      setBusy("");
    }
  }

  async function print() {
    if (!path) return;
    setBusy("print");
    try {
      setPrintData(await api<ReportData>(`${path}${query({ ...params, page_size: "print" })}`));
    } catch (err) {
      toast("error", err instanceof ApiError ? err.message : "Could not prepare the report.");
      setBusy("");
    }
  }
  const printReady = useCallback(() => {
    window.print();
    setPrintData(null);
    setBusy("");
  }, []);

  const parsed = parseSearch(search);
  const known = new Set(report?.tokens.map((t) => t.key));
  const removeToken = (raw: string) => setSearch((s) => s.replace(raw, "").replace(/\s+/g, " ").trim());
  const addToken = (key: string) => {
    setSearch((s) => `${s.trim()} ${key}:`.trimStart());
    setTimeout(() => searchBox.current?.focus(), 0);
  };

  // What narrows the report beyond the period and search, shown as removable chips while the panel is closed.
  const active = [
    ...(sites === "all" || sites.length !== 1 || sites[0] !== condo.id
      ? [{ key: "sites", text: `Sites: ${sites === "all" ? "All sites" : sites.length === 1 ? catalog?.sites.find((x) => x.id === sites[0])?.name ?? "1 site" : `${sites.length} sites`}`,
           clear: () => setSites([condo.id]) }] : []),
    ...(preset === "custom" ? [{ key: "range", text: `${formatDate(range.from)} – ${formatDate(range.to)}`, clear: () => pickPreset("7d") }] : []),
    ...(report?.filters ?? []).filter((f) => filters[f.name]).map((f) => ({
      key: f.name, text: `${f.label}: ${f.options.find((o) => o.value === filters[f.name])?.label ?? filters[f.name]}`,
      clear: () => setFilters((v) => ({ ...v, [f.name]: "" })),
    })),
  ];

  if (catalogError) return <><PageHeader title="Reports" /><ErrorNote error={catalogError} /></>;
  if (!catalog || !report) return <Loading />;

  return (
    <>
      <PageHeader
        title="Reports"
        description={catalog.can_combine
          ? "Consolidated reports across your sites. Pick a report, the sites and the period, then print or export."
          : `Reports for ${condo.name}. Pick a report and the period, then print or export.`}
        action={advanced ? (
          <>
            <Button onClick={print} busy={busy === "print"} disabled={!!busy || !data}><Icon name="printer" className="h-4 w-4" /> Print / PDF</Button>
            <Button onClick={() => download("xlsx")} busy={busy === "xlsx"} disabled={!!busy || !data}><Icon name="download" className="h-4 w-4" /> Excel</Button>
            <Button variant="ghost" onClick={() => download("csv")} busy={busy === "csv"} disabled={!!busy || !data}>CSV</Button>
          </>
        ) : (
          <span className="inline-flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-sm text-muted" title="Print and export are part of Advanced reports.">
            <Icon name="lock" className="h-4 w-4" /> Print &amp; export · {upsellText(advancedInfo)}
          </span>
        )}
      />

      {/* Report types as one row of tabs, then the chosen report's filters. */}
      <Card className="mb-5">
        <Tabs active={report.key} onChange={choose}
          tabs={catalog.reports.map((r) => ({ key: r.key, label: TAB_LABEL[r.key] ?? r.title }))} />
        <p className="px-4 pt-3 text-sm text-muted">{report.description}</p>
        {/* Always visible: period, smart search and the Filters button. */}
        <div className="flex flex-wrap items-center gap-2 p-4">
          <Select value={preset} onChange={(e) => pickPreset(e.target.value as Preset)} aria-label="Period" className="w-full sm:w-44">
            {PRESETS.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
          </Select>
          <div className="relative min-w-0 flex-1 basis-56">
            <Icon name="search" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <Input ref={searchBox} value={search} onChange={(e) => setSearch(e.target.value)} className="pl-9"
              placeholder={`Smart search: any words, or ${report.tokens.slice(0, 3).map((t) => `${t.key}:…`).join(" ")}`} aria-label="Smart search" />
          </div>
          <Button onClick={() => togglePanel()} aria-expanded={panel} aria-controls="report-filters">
            <Icon name="sliders" className="h-4 w-4" /> Filters
            {active.length > 0 && <span className="rounded-full bg-primary-500/15 px-1.5 text-xs font-semibold text-primary-700 dark:text-primary-300">{active.length}</span>}
            <Icon name="chevron" className={cx("h-4 w-4 transition-transform", panel ? "-rotate-90" : "rotate-90")} />
          </Button>
        </div>

        {/* Active filters and search tokens, removable with one click. */}
        {(active.length > 0 || parsed.tokens.length > 0 || parsed.words.length > 0) && (
          <div className="-mt-1 flex flex-wrap items-center gap-1.5 px-4 pb-4 text-xs">
            {active.map((c) => (
              <button key={c.key} type="button" onClick={c.clear} title="Remove"
                className="inline-flex items-center gap-1 rounded-full bg-surface-3 px-2.5 py-1 font-medium text-body ring-1 ring-inset ring-line hover:text-ink">
                {c.text} <Icon name="x" className="h-3 w-3" />
              </button>
            ))}
            {parsed.tokens.map((t) => (
              <button key={t.raw} type="button" onClick={() => removeToken(t.raw)} title="Remove"
                className={cx("inline-flex items-center gap-1 rounded-full px-2.5 py-1 font-medium ring-1 ring-inset",
                  known.has(t.key) ? "bg-primary-500/10 text-primary-700 ring-primary-600/25 dark:text-primary-300" : "bg-amber-500/10 text-amber-800 ring-amber-600/25 dark:text-amber-300")}>
                {t.key}: {t.value || "…"}{!known.has(t.key) && " (searched as text)"} <Icon name="x" className="h-3 w-3" />
              </button>
            ))}
            {parsed.words.map((w, i) => <span key={`${w}-${i}`} className="rounded-full bg-surface-3 px-2.5 py-1 text-body">“{w}”</span>)}
          </div>
        )}

        {panel && (
          <div id="report-filters" className="border-t border-line p-4">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Field label={catalog.can_combine ? "Sites" : "Site"}><SitePicker catalog={catalog} value={sites} onChange={setSites} /></Field>
              <Field label="From">
                <Input type="date" value={range.from} max={range.to} onChange={(e) => { setPreset("custom"); setRange((r) => ({ ...r, from: e.target.value })); }} />
              </Field>
              <Field label="To">
                <Input type="date" value={range.to} min={range.from} onChange={(e) => { setPreset("custom"); setRange((r) => ({ ...r, to: e.target.value })); }} />
              </Field>
              {report.filters.map((f) => (
                <Field key={f.name} label={f.label}>
                  <Select value={filters[f.name] ?? ""} onChange={(e) => setFilters((v) => ({ ...v, [f.name]: e.target.value }))}>
                    <option value="">All</option>
                    {f.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </Select>
                </Field>
              ))}
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-1.5 text-xs">
              <span className="text-muted">Search by:</span>
              {report.tokens.map((t) => (
                <button key={t.key} type="button" onClick={() => addToken(t.key)} title={t.help}
                  className="rounded-full border border-line px-2.5 py-1 font-mono text-body hover:border-primary-400 hover:text-ink">{t.key}:</button>
              ))}
            </div>
          </div>
        )}
      </Card>

      {error && <div className="mb-5"><ErrorNote error={error} /></div>}
      {!data ? (isLoading ? <Loading /> : null) : (
        <div className={cx("space-y-5 transition-opacity", isLoading && "opacity-60")}>
          {/* Key figures */}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            {data.summary.kpis.map((k) => (
              <Card key={k.key} className="p-4">
                <div className="text-xs font-medium text-muted">{k.label}</div>
                <div className="mt-1 text-2xl font-semibold tabular-nums tracking-tight text-ink">{formatKpi(k)}</div>
              </Card>
            ))}
          </div>

          <div className="grid gap-5 xl:grid-cols-[1.4fr_1fr]">
            <Card>
              <CardHeader title={`Daily trend · ${data.period.label}`} />
              <div className="p-5"><DailyChart points={data.summary.trend.points} series={data.summary.trend.series} label={dayLabel} /></div>
            </Card>
            <div className="grid gap-5 sm:grid-cols-2">
              {data.summary.breakdowns.slice(0, 4).map((b) => (
                <Card key={b.key}>
                  <CardHeader title={b.title} />
                  <div className="p-5">{b.rows.length ? <BarList rows={b.rows.slice(0, 6)} /> : <p className="text-sm text-muted">No data.</p>}</div>
                </Card>
              ))}
            </div>
          </div>

          {data.summary.insights_locked && (
            <Card className="flex flex-wrap items-center gap-3 p-5">
              <Icon name="lock" className="h-5 w-5 text-muted" />
              <div className="min-w-0 flex-1 text-sm">
                <div className="font-medium text-ink">Busiest times, visits per day by category and average stay</div>
                <div className="text-muted">Part of Advanced reports · {upsellText(advancedInfo)}</div>
              </div>
            </Card>
          )}
          {data.summary.insights && (
            <>
              <Card>
                <CardHeader title="Busiest times" action={<span className="text-xs text-muted">Arrivals by weekday and hour (SGT) · for planning shifts</span>} />
                <div className="p-5"><Heatmap grid={data.summary.insights.heatmap} what="arrivals" /></div>
              </Card>
              <div className="grid gap-5 xl:grid-cols-[1.4fr_1fr]">
                <Card>
                  <CardHeader title="Visits per day by category" />
                  <div className="p-5">
                    <DailyChart points={data.summary.insights.purpose_trend.points} series={data.summary.insights.purpose_trend.series} label={dayLabel} />
                  </div>
                </Card>
                <Card>
                  <CardHeader title="Average stay by category" action={<span className="text-xs text-muted">Visitors who checked out</span>} />
                  <div className="p-5">
                    {data.summary.insights.stay_by_purpose.length ? (
                      <BarList rows={data.summary.insights.stay_by_purpose.map((r) => ({ label: `${r.label} (${r.visits})`, value: r.minutes }))}
                        format={(m) => (m >= 60 ? `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m` : `${m}m`)} />
                    ) : <p className="text-sm text-muted">Nobody checked out in this period.</p>}
                  </div>
                </Card>
              </div>
            </>
          )}

          <Card>
            <CardHeader
              title={<>Details <span className="ml-1 text-sm font-normal text-muted">{data.count.toLocaleString("en-SG")} record{data.count === 1 ? "" : "s"}</span></>}
              action={<span className="text-xs text-muted">{data.sites.length > 1 ? `${data.sites.length} sites · ` : ""}{data.period.label}</span>}
            />
            {data.rows.length === 0 ? <Empty>Nothing matches this period and these filters.</Empty> : (
              <Table>
                <thead><tr>{data.columns.map((c) => <Th key={c.key} className={c.kind === "number" ? "text-right" : undefined}>{c.label}</Th>)}</tr></thead>
                <tbody className="divide-y divide-line">
                  {data.rows.map((row, i) => (
                    <tr key={i}>
                      {data.columns.map((c) => {
                        const text = formatCell(row[c.key], c.kind);
                        return (
                          <Td key={c.key} className={cx(c.kind === "number" && "text-right tabular-nums", (c.kind === "datetime" || c.kind === "date") && "whitespace-nowrap",
                            c.key === "pass" && "font-mono font-semibold text-ink", c.key === "notes" && "max-w-xs truncate")}>
                            {c.kind === "badge" && text !== "—" ? <Badge tone={badgeTone(text)}>{text}</Badge> : text}
                          </Td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
            <Pagination page={page} count={data.count} pageSize={PAGE_SIZE} onPage={setPage} />
          </Card>
        </div>
      )}

      {printData && <ReportPrint data={printData} onReady={printReady} />}
    </>
  );
}
