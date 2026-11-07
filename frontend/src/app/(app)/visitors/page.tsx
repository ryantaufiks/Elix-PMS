"use client";

import { useState } from "react";
import useSWR from "swr";

import { SearchInput } from "@/components/bits";
import { ConfirmDialog, EntityModal, remove } from "@/components/forms";
import { Badge, Button, Card, Empty, Loading, PageHeader, Pagination, Select, Table, Td, Th } from "@/components/ui";
import { query } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Page, Visitor } from "@/lib/types";

export default function VisitorsPage() {
  const { condo, isAdmin } = useSession();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("");
  const [page, setPage] = useState(1);
  const [blocking, setBlocking] = useState<Visitor | null>(null);
  const [erasing, setErasing] = useState<Visitor | null>(null);
  const { data, mutate } = useSWR<Page<Visitor>>(
    `/v1/visitors/${query({ condominium: condo.id, search, is_blacklisted: filter, ordering: "-last_visit_at", page })}`,
    { keepPreviousData: true },
  );

  return (
    <>
      <PageHeader
        title="Visitors"
        description={`People who identified themselves at the kiosk. Details are deleted ${condo.visitor_data_retention_days} days after their last visit (PDPA), except blocked visitors.`}
      />
      <Card>
        <div className="flex flex-wrap gap-2 border-b border-line p-4">
          <SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Name, mobile, NRIC last 4, company" />
          <Select value={filter} onChange={(e) => { setFilter(e.target.value); setPage(1); }} className="sm:w-44" aria-label="Status">
            <option value="">All visitors</option>
            <option value="true">Blocked only</option>
          </Select>
        </div>
        {!data ? <Loading /> : data.results.length === 0 ? <Empty>No visitors yet.</Empty> : (
          <Table>
            <thead><tr><Th>Name</Th><Th>Mobile</Th><Th>NRIC/FIN</Th><Th>Company</Th><Th>Last visit</Th><Th>Status</Th><Th /></tr></thead>
            <tbody className="divide-y divide-line">
              {data.results.map((v) => (
                <tr key={v.id}>
                  <Td className="font-medium text-ink">{v.full_name}</Td>
                  <Td>{v.phone || "—"}</Td>
                  <Td className="font-mono text-xs">{v.id_partial ? `•••••${v.id_partial}` : "—"}</Td>
                  <Td>{v.company || "—"}</Td>
                  <Td className="whitespace-nowrap">{v.last_visit_at ? formatDateTime(v.last_visit_at) : "—"}</Td>
                  <Td>
                    {v.is_blacklisted
                      ? <span title={v.blacklist_reason}><Badge tone="red">Blocked</Badge>{v.blacklist_reason && <div className="mt-1 max-w-xs text-xs text-muted">{v.blacklist_reason}</div>}</span>
                      : <Badge tone="green">Allowed</Badge>}
                  </Td>
                  <Td className="whitespace-nowrap text-right">
                    <Button size="sm" variant="ghost" onClick={() => setBlocking(v)}>{v.is_blacklisted ? "Unblock" : "Block"}</Button>
                    {isAdmin && <Button size="sm" variant="ghost" onClick={() => setErasing(v)}>Erase data</Button>}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        {data && <Pagination page={page} count={data.count} onPage={setPage} />}
      </Card>

      {blocking && (
        <EntityModal
          title={blocking.is_blacklisted ? `Unblock ${blocking.full_name}?` : `Block ${blocking.full_name}`}
          submitLabel={blocking.is_blacklisted ? "Unblock" : "Block visitor"}
          fields={blocking.is_blacklisted ? [] : [{ name: "blacklist_reason", label: "Reason (staff only)", type: "textarea", required: true }]}
          record={blocking}
          endpoint={`/v1/visitors/${blocking.id}/`}
          extra={{ is_blacklisted: !blocking.is_blacklisted, ...(blocking.is_blacklisted ? { blacklist_reason: "" } : {}) }}
          onClose={() => setBlocking(null)}
          onSaved={() => { setBlocking(null); mutate(); }}
        />
      )}
      <ConfirmDialog
        open={!!erasing}
        title="Erase this visitor's data?"
        confirmLabel="Erase permanently"
        onClose={() => setErasing(null)}
        message={<>For a PDPA deletion request: removes <strong>{erasing?.full_name}</strong>, their photos and their details from calls and invitations. Access-log entries remain without personal details. This cannot be undone.</>}
        onConfirm={async () => { await remove(`/v1/visitors/${erasing!.id}/`); mutate(); }}
      />
    </>
  );
}
