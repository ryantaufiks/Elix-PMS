"use client";

import { useState } from "react";
import useSWR from "swr";

import { SearchInput } from "@/components/bits";
import { ConfirmDialog, EntityModal, remove } from "@/components/forms";
import { Badge, Button, Card, Empty, Loading, Modal, PageHeader, Pagination, Select, Table, Td, Th } from "@/components/ui";
import { query } from "@/lib/api";
import { formatDateTime, visitPurpose } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Page, Visit, Visitor, VisitState } from "@/lib/types";

const STATE: Record<VisitState, { label: string; tone: "green" | "slate" | "amber" }> = {
  on_site: { label: "On site", tone: "green" },
  checked_out: { label: "Checked out", tone: "slate" },
  expired: { label: "Not checked out", tone: "amber" },
};

const when = (iso: string | null) => (iso ? formatDateTime(iso) : "—");

/** Every visit of one visitor, newest first: when they came in and when they left. */
function History({ visitor, onClose }: { visitor: Visitor; onClose: () => void }) {
  const [page, setPage] = useState(1);
  const { data } = useSWR<Page<Visit>>(`/v1/visits/${query({ visitor: visitor.id, page })}`, { keepPreviousData: true });
  return (
    <Modal open onClose={onClose} wide title={`Visits · ${visitor.full_name}`}>
      {!data ? <Loading /> : data.results.length === 0 ? <Empty>No visits recorded yet.</Empty> : (
        <Table>
          <thead><tr><Th>Pass</Th><Th>Visiting</Th><Th>Check-in</Th><Th>Check-out</Th><Th>Status</Th></tr></thead>
          <tbody className="divide-y divide-line">
            {data.results.map((v) => (
              <tr key={v.id}>
                <Td className="font-mono font-semibold text-ink">{v.pass_number}</Td>
                <Td>
                  {v.unit_display}
                  <div className="text-xs text-muted">{[visitPurpose(v.purpose), v.source_display].filter(Boolean).join(" · ")}</div>
                </Td>
                <Td className="whitespace-nowrap">{when(v.created_at)}</Td>
                <Td className="whitespace-nowrap">
                  {when(v.checked_out_at)}
                  {v.checked_out_at && <div className="text-xs text-muted">{v.checked_out_by_name || "Self / exit camera"}</div>}
                </Td>
                <Td><Badge tone={STATE[v.state].tone}>{STATE[v.state].label}</Badge></Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      {data && <Pagination page={page} count={data.count} onPage={setPage} />}
    </Modal>
  );
}

export default function VisitorsPage() {
  const { condo, isAdmin } = useSession();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("");
  const [page, setPage] = useState(1);
  const [blocking, setBlocking] = useState<Visitor | null>(null);
  const [erasing, setErasing] = useState<Visitor | null>(null);
  const [history, setHistory] = useState<Visitor | null>(null);
  const { data, mutate } = useSWR<Page<Visitor>>(
    `/v1/visitors/${query({ condominium: condo.id, search, is_blacklisted: filter, ordering: "-last_visit_at", page })}`,
    { keepPreviousData: true },
  );

  return (
    <>
      <PageHeader
        title="Visitor records"
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
            <thead><tr><Th>Name</Th><Th>Mobile</Th><Th>NRIC/FIN</Th><Th>Company</Th><Th>Last check-in</Th><Th>Last check-out</Th><Th>Status</Th><Th /></tr></thead>
            <tbody className="divide-y divide-line">
              {data.results.map((v) => (
                <tr key={v.id}>
                  <Td className="font-medium text-ink">{v.full_name}</Td>
                  <Td>{v.phone || "—"}</Td>
                  <Td className="font-mono text-xs">{v.id_partial ? `•••••${v.id_partial}` : "—"}</Td>
                  <Td>{v.company || "—"}</Td>
                  <Td className="whitespace-nowrap">{when(v.last_check_in ?? v.last_visit_at)}</Td>
                  <Td className="whitespace-nowrap">{v.on_site ? <Badge tone="green">On site</Badge> : when(v.last_check_out)}</Td>
                  <Td>
                    {v.is_blacklisted
                      ? <span title={v.blacklist_reason}><Badge tone="red">Blocked</Badge>{v.blacklist_reason && <div className="mt-1 max-w-xs text-xs text-muted">{v.blacklist_reason}</div>}</span>
                      : <Badge tone="green">Allowed</Badge>}
                  </Td>
                  <Td className="whitespace-nowrap text-right">
                    <Button size="sm" variant="ghost" onClick={() => setHistory(v)}>Visits{v.visit_count ? ` (${v.visit_count})` : ""}</Button>
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
      {history && <History visitor={history} onClose={() => setHistory(null)} />}
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
