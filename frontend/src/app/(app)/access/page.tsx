"use client";

import { useCallback, useState } from "react";
import useSWR from "swr";

import { AccessTable } from "@/components/AccessTable";
import { SearchInput, useGates } from "@/components/bits";
import { Button, Card, ErrorNote, Input, Loading, PageHeader, Pagination, Select } from "@/components/ui";
import { query } from "@/lib/api";
import { fromLocalInput, METHOD_LABEL } from "@/lib/format";
import { useLiveEvents } from "@/lib/live";
import { useSession } from "@/lib/session";
import type { AccessLog, Page } from "@/lib/types";

const EMPTY = { gate: "", method: "", result: "", search: "", from: "", to: "" };

export default function AccessLogPage() {
  const { condo } = useSession();
  const gates = useGates(condo.id);
  const [filters, setFilters] = useState(EMPTY);
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
      occurred_at__gte: fromLocalInput(filters.from), occurred_at__lte: fromLocalInput(filters.to),
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
          <Input type="datetime-local" value={filters.from} onChange={(e) => set("from", e.target.value)} className="sm:w-52" aria-label="From (SGT)" title="From (SGT)" />
          <Input type="datetime-local" value={filters.to} onChange={(e) => set("to", e.target.value)} className="sm:w-52" aria-label="To (SGT)" title="To (SGT)" />
          {filtered && <Button variant="ghost" onClick={() => { setFilters(EMPTY); setPage(1); }}>Clear</Button>}
        </div>
        {error && <div className="p-3"><ErrorNote error={error} /></div>}
        {data ? <AccessTable logs={data.results} highlight={fresh} /> : !error && <Loading />}
        {data && <Pagination page={page} count={data.count} onPage={setPage} />}
      </Card>
    </>
  );
}
