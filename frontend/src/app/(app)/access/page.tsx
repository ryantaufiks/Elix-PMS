"use client";

import { useCallback, useState } from "react";
import useSWR from "swr";

import { AccessTable } from "@/components/AccessTable";
import { SearchInput, useGates } from "@/components/bits";
import { Button, Card, cx, ErrorNote, Input, Loading, PageHeader, Pagination, Select } from "@/components/ui";
import { query } from "@/lib/api";
import { METHOD_LABEL, sgDate } from "@/lib/format";
import { useLiveEvents } from "@/lib/live";
import { useSession } from "@/lib/session";
import type { AccessLog, Page } from "@/lib/types";

const EMPTY = { gate: "", method: "", result: "", search: "", from: "", to: "" };
// Period presets: whole SGT days, so "Today" is 00:00 to now and "7 days" includes today.
const PERIODS = [
  { key: "all", label: "All time", from: () => "" },
  { key: "today", label: "Today", from: () => sgDate(0) },
  { key: "7d", label: "7 days", from: () => sgDate(-6) },
  { key: "30d", label: "30 days", from: () => sgDate(-29) },
  { key: "custom", label: "Custom", from: () => "" },
] as const;
type Period = (typeof PERIODS)[number]["key"];

export default function AccessLogPage() {
  const { condo } = useSession();
  const gates = useGates(condo.id);
  const [filters, setFilters] = useState(EMPTY);
  const [period, setPeriod] = useState<Period>("all");
  const [page, setPage] = useState(1);
  const [fresh, setFresh] = useState<Set<number>>(new Set());
  const set = useCallback((key: keyof typeof EMPTY, value: string) => {
    setFilters((f) => ({ ...f, [key]: value }));
    setPage(1);
  }, []);

  const filtered = Object.values(filters).some(Boolean);
  const { data, error, mutate } = useSWR<Page<AccessLog>>(
    `/v1/access-logs/${query({
      condominium: condo.id, page, gate: filters.gate, method: filters.method, result: filters.result, search: filters.search,
      occurred_at__gte: filters.from ? `${filters.from}T00:00:00+08:00` : "", occurred_at__lte: filters.to ? `${filters.to}T23:59:59+08:00` : "",
    })}`,
    { keepPreviousData: true },
  );

  useLiveEvents((event) => {
    if (event.type !== "access_log" || event.data.condominium !== condo.id) return;
    if (page === 1 && !filtered) {
      mutate((p) => p && { ...p, count: p.count + 1, results: [event.data, ...p.results].slice(0, 50) }, { revalidate: false });
      setFresh((s) => new Set(s).add(event.data.id));
    }
  });

  return (
    <>
      <PageHeader title="Access log" description="Every gate decision: licence plates, QR invitations, intercom and manual openings." />
      <Card>
        <div className="flex flex-wrap gap-2 border-b border-line p-3">
          <SearchInput value={filters.search} onChange={(v) => set("search", v)} placeholder="Plate or reason" />
          <Select value={filters.gate} onChange={(e) => set("gate", e.target.value)} className="sm:w-44" aria-label="Gate">
            <option value="">All gates</option>
            {gates.data?.results.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
          </Select>
          <Select value={filters.method} onChange={(e) => set("method", e.target.value)} className="sm:w-44" aria-label="Method">
            <option value="">All methods</option>
            {Object.entries(METHOD_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
          <Select value={filters.result} onChange={(e) => set("result", e.target.value)} className="sm:w-36" aria-label="Result">
            <option value="">All results</option>
            <option value="granted">Granted</option>
            <option value="denied">Denied</option>
            <option value="error">Error</option>
          </Select>
          {filtered && <Button variant="ghost" onClick={() => { setFilters(EMPTY); setPeriod("all"); setPage(1); }}>Clear</Button>}
        </div>
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
          <div className="flex max-w-full overflow-x-auto rounded-lg border border-line bg-surface-2 p-0.5 whitespace-nowrap" role="group" aria-label="Period">
            {PERIODS.map((p) => (
              <button key={p.key} type="button" onClick={() => { setPeriod(p.key); setFilters((f) => ({ ...f, from: p.from(), to: p.key === "custom" ? f.to : "" })); setPage(1); }}
                className={cx("rounded-md px-3 py-1.5 text-sm font-medium transition", period === p.key ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink")}>
                {p.label}
              </button>
            ))}
          </div>
          {period === "custom" && (
            <>
              <Input type="date" value={filters.from} max={filters.to || undefined} onChange={(e) => set("from", e.target.value)} className="sm:w-40" aria-label="From date" />
              <span className="text-sm text-muted">to</span>
              <Input type="date" value={filters.to} min={filters.from || undefined} onChange={(e) => set("to", e.target.value)} className="sm:w-40" aria-label="To date" />
            </>
          )}
          <span className="ml-auto text-xs text-muted">Times are Singapore time</span>
        </div>
        {error && <div className="p-3"><ErrorNote error={error} /></div>}
        {data ? <AccessTable logs={data.results} highlight={fresh} /> : !error && <Loading />}
        {data && <Pagination page={page} count={data.count} onPage={setPage} />}
      </Card>
    </>
  );
}
