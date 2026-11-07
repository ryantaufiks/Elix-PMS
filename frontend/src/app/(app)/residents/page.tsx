"use client";

import { useState } from "react";
import useSWR from "swr";

import { SearchInput } from "@/components/bits";
import { Badge, Card, Empty, Loading, PageHeader, Pagination, Select, Table, Td, Th } from "@/components/ui";
import { query } from "@/lib/api";
import { RESIDENT_TYPE_LABEL, userName } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Page, Residency, Unit } from "@/lib/types";

export default function ResidentsPage() {
  const { condo, me } = useSession();
  const [search, setSearch] = useState("");
  const [type, setType] = useState("");
  const [page, setPage] = useState(1);
  const { data } = useSWR<Page<Residency>>(
    `/v1/residencies/${query({ unit__condominium: condo.id, is_active: true, resident_type: type, search: search.replace("#", ""), page })}`,
    { keepPreviousData: true },
  );
  const units = useSWR<Page<Unit>>(`/v1/units/${query({ condominium: condo.id, page_size: 200 })}`);
  const unitName = (id: number) => units.data?.results.find((u) => u.id === id)?.display_name ?? `Unit ${id}`;

  return (
    <>
      <PageHeader
        title="Residents"
        description={`Who lives where, and who answers intercom calls.${me.is_superuser ? " Add or move residents in Django admin." : ""}`}
      />
      <Card>
        <div className="flex flex-wrap gap-2 border-b border-slate-100 p-3">
          <SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Name or unit number" />
          <Select value={type} onChange={(e) => { setType(e.target.value); setPage(1); }} className="sm:w-40" aria-label="Resident type">
            <option value="">All types</option>
            {Object.entries(RESIDENT_TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
        </div>
        {!data ? (
          <Loading />
        ) : data.results.length === 0 ? (
          <Empty>No residents found.</Empty>
        ) : (
          <Table>
            <thead><tr><Th>Unit</Th><Th>Resident</Th><Th>Type</Th><Th>Contact</Th><Th>Intercom</Th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {data.results.map((r) => (
                <tr key={r.id}>
                  <Td className="whitespace-nowrap">{unitName(r.unit)}</Td>
                  <Td>
                    <span className="font-medium text-slate-800">{userName(r.user_detail)}</span>
                    {r.is_primary_contact && <span className="ml-2"><Badge tone="blue">Primary</Badge></span>}
                  </Td>
                  <Td>{RESIDENT_TYPE_LABEL[r.resident_type]}</Td>
                  <Td className="text-xs text-slate-500">
                    {r.user_detail.phone && <div>{r.user_detail.phone}</div>}
                    {r.user_detail.email && <div>{r.user_detail.email}</div>}
                  </Td>
                  <Td>{r.receives_intercom_calls ? <Badge tone="green">Receives calls</Badge> : <Badge>Muted</Badge>}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        {data && <Pagination page={page} count={data.count} onPage={setPage} />}
      </Card>
    </>
  );
}
