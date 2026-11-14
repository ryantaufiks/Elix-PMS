"use client";

import { useState } from "react";
import useSWR from "swr";

import { SearchInput } from "@/components/bits";
import { Tabs } from "@/components/forms";
import { Icon } from "@/components/icons";
import { ModuleGate } from "@/components/ModuleGate";
import { Badge, Button, Card, Empty, ErrorNote, Field, Input, Loading, Modal, PageHeader, Pagination, Table, Td, Textarea, Th, type Tone, useToast } from "@/components/ui";
import { api, query } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import { useLiveEvents } from "@/lib/live";
import { useSession } from "@/lib/session";
import type { Page, RenovationPermit } from "@/lib/types";

const STATUS_TONE: Record<RenovationPermit["status"], Tone> = {
  pending_payment: "amber", submitted: "amber", approved: "green", rejected: "red", cancelled: "slate", completed: "blue",
};
type Tab = "waiting" | "open" | "all";

/** e-Permit to Work: residents apply in the app; the management office approves, completes and refunds. */
function PermitsPage() {
  const { condo, isManager } = useSession();
  const [tab, setTab] = useState<Tab>("waiting");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<RenovationPermit | null>(null);
  const filters = tab === "waiting" ? { status: "submitted" } : tab === "open" ? { open: 1 } : {};
  const { data, mutate } = useSWR<Page<RenovationPermit>>(`/v1/renovation-permits/${query({ condominium: condo.id, search, page, ...filters })}`,
    { keepPreviousData: true });
  const waiting = useSWR<Page<RenovationPermit>>(`/v1/renovation-permits/${query({ condominium: condo.id, status: "submitted", page_size: 1 })}`);
  useLiveEvents((event) => { if (event.type === "permit") { mutate(); waiting.mutate(); } });

  return (
    <>
      <PageHeader title="Renovation permits"
        description="Residents apply in the app with their contractor, the work and the dates. Approving issues the contractor's pass for those dates on the site's contractor days and hours." />
      <Card>
        <Tabs active={tab} onChange={(t) => { setTab(t); setPage(1); }} tabs={[
          { key: "waiting", label: "Waiting for approval", count: waiting.data?.count }, { key: "open", label: "Open" }, { key: "all", label: "All" },
        ]} />
        <div className="border-b border-line p-3">
          <SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Contractor, unit or work" />
        </div>
        {!data ? <Loading /> : data.results.length === 0 ? (
          <Empty icon="file" title={tab === "waiting" ? "Nothing to approve" : "No permits"}>
            Residents apply from the app once Renovation permits are on (Site settings → Renovation permits).
          </Empty>
        ) : (
          <Table>
            <thead><tr><Th>Unit</Th><Th>Contractor</Th><Th>Work</Th><Th>Dates</Th><Th>Deposit</Th><Th>Status</Th><Th /></tr></thead>
            <tbody className="divide-y divide-line">
              {data.results.map((p) => (
                <tr key={p.id}>
                  <Td>{p.unit_display}<div className="text-xs text-muted">{p.applicant_name}</div></Td>
                  <Td className="font-medium text-ink">{p.contractor_company}<div className="text-xs font-normal text-muted">{p.workers} worker{p.workers === 1 ? "" : "s"}</div></Td>
                  <Td>{p.category_display}{p.description && <div className="max-w-56 truncate text-xs text-muted">{p.description}</div>}</Td>
                  <Td className="whitespace-nowrap">{formatDate(p.start_date)} – {formatDate(p.end_date)}</Td>
                  <Td className="whitespace-nowrap tabular-nums">{Number(p.deposit) ? `${p.currency} ${p.deposit}` : "—"}
                    {Number(p.deposit) > 0 && <div className="text-xs text-muted">{p.payment_status_display}</div>}</Td>
                  <Td><Badge tone={STATUS_TONE[p.status]}>{p.status_display}</Badge></Td>
                  <Td className="text-right"><Button size="sm" variant={p.status === "submitted" && isManager ? "primary" : "ghost"} onClick={() => setOpen(p)}>
                    {p.status === "submitted" && isManager ? "Review" : "View"}</Button></Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        {data && <Pagination page={page} count={data.count} onPage={setPage} />}
      </Card>
      {open && <PermitDetail permit={open} canManage={isManager} onClose={() => setOpen(null)}
        onChanged={(p) => { setOpen(p); mutate(); waiting.mutate(); }} />}
    </>
  );
}

function PermitDetail({ permit, canManage, onClose, onChanged }: {
  permit: RenovationPermit; canManage: boolean; onClose: () => void; onChanged: (p: RenovationPermit) => void;
}) {
  const toast = useToast();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState<unknown>(null);

  async function act(action: string, body?: object, message?: string) {
    setBusy(action);
    setError(null);
    try {
      const updated = await api<RenovationPermit>(`/v1/renovation-permits/${permit.id}/${action}/`, { method: "POST", body: body ?? {} });
      if (message) toast("success", message);
      onChanged(updated);
    } catch (err) {
      setError(err);
    } finally {
      setBusy("");
    }
  }

  async function upload(file: File | undefined) {
    if (!file) return;
    const form = new FormData();
    form.set("file", file);
    await act("document", form, "Document attached.");
  }

  async function download() {
    const response = await api<Response>(`/v1/renovation-permits/${permit.id}/document/`, { raw: true });
    const url = URL.createObjectURL(await response.blob());
    Object.assign(document.createElement("a"), { href: url, download: permit.document_name || "document" }).click();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  const rows: [string, React.ReactNode][] = [
    ["Unit", `${permit.unit_display}${permit.applicant_name ? ` · ${permit.applicant_name}` : ""}`],
    ["Work", `${permit.category_display}${permit.description ? `: ${permit.description}` : ""}`],
    ["Contractor", [permit.contractor_company, permit.contractor_contact, permit.contractor_phone].filter(Boolean).join(" · ")],
    ["Workers", String(permit.workers)],
    ["Dates", `${formatDate(permit.start_date)} – ${formatDate(permit.end_date)}`],
    ["Vehicles", permit.plates.join(", ") || "—"],
    ["Deposit", Number(permit.deposit) ? `${permit.currency} ${permit.deposit} · ${permit.payment_status_display}` : "None online"],
    ["Applied", formatDateTime(permit.created_at)],
    ...(permit.decided_at ? [[permit.status === "rejected" ? "Rejected" : "Decided", `${formatDateTime(permit.decided_at)} · ${permit.decided_by_name}${permit.decision_note ? ` · ${permit.decision_note}` : ""}`] as [string, string]] : []),
  ];

  return (
    <Modal open onClose={onClose} title={`Renovation permit · ${permit.unit_display}`} wide>
      <div className="space-y-4">
        <ErrorNote error={error} />
        <div className="flex items-center gap-2"><Badge tone={STATUS_TONE[permit.status]}>{permit.status_display}</Badge></div>
        <dl className="divide-y divide-line rounded-lg border border-line text-sm">
          {rows.map(([k, v]) => (
            <div key={k} className="flex gap-4 px-4 py-2.5"><dt className="w-28 shrink-0 text-muted">{k}</dt><dd className="text-ink">{v}</dd></div>
          ))}
        </dl>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted">Document:</span>
          {permit.has_document
            ? <button type="button" className="font-medium text-primary-600 hover:underline dark:text-primary-300" onClick={download}>{permit.document_name}</button>
            : <span className="text-muted">none</span>}
          {canManage && (
            <label className="cursor-pointer rounded-md border border-line px-2.5 py-1 text-body hover:bg-surface-2">
              <Icon name="file" className="mr-1 inline h-4 w-4" />{permit.has_document ? "Replace" : "Attach insurance or drawings"}
              <input type="file" accept="application/pdf,image/jpeg,image/png" className="sr-only" onChange={(e) => upload(e.target.files?.[0])} />
            </label>
          )}
        </div>
        {permit.pass_url && (
          <Field label="Contractor's pass" hint="Also in the resident's app to share. Works on the site's contractor days and hours within the dates.">
            <div className="flex gap-2"><Input readOnly value={permit.pass_url} onFocus={(e) => e.target.select()} />
              <Button onClick={() => navigator.clipboard?.writeText(permit.pass_url).then(() => toast("success", "Link copied."))}>Copy</Button></div>
          </Field>
        )}
        {canManage && permit.status === "submitted" && (
          <div className="space-y-3 rounded-lg border border-line p-4">
            <Field label="Note to the resident (optional)" hint="Conditions on approval, or why it is rejected.">
              <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. No hacking after 5 pm; protect the lift with boards." />
            </Field>
            <div className="flex flex-wrap justify-end gap-2">
              <Button variant="danger" busy={busy === "reject"} onClick={() => act("reject", { note }, "Permit rejected.")}>Reject</Button>
              <Button variant="primary" busy={busy === "approve"} onClick={() => act("approve", { note }, "Permit approved. The contractor's pass is issued.")}>Approve</Button>
            </div>
          </div>
        )}
        {canManage && (
          <div className="flex flex-wrap justify-end gap-2">
            {permit.status === "approved" && <Button busy={busy === "complete"} onClick={() => act("complete", undefined, "Permit completed. The contractor's pass has ended.")}>Mark works completed</Button>}
            {["pending_payment", "submitted", "approved"].includes(permit.status) && (
              <Button variant="ghost" busy={busy === "cancel"} onClick={() => act("cancel", undefined, "Permit cancelled.")}>Cancel permit</Button>
            )}
            {permit.payment_status === "paid" && ["completed", "rejected", "cancelled"].includes(permit.status) && (
              <Button busy={busy === "refunded"} onClick={() => act("refunded", undefined, "Deposit refund recorded.")}>Deposit refunded</Button>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}

export default function Page() {
  return <ModuleGate module="resident_app"><PermitsPage /></ModuleGate>;
}
