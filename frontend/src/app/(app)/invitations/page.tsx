"use client";

import { useState } from "react";
import useSWR from "swr";

import { AuthImage, SearchInput, UnitPicker, useGates } from "@/components/bits";
import { Badge, Button, Card, Checkbox, Empty, ErrorNote, Field, Input, Loading, Modal, PageHeader, Pagination, Select, Table, Td, Textarea, Th, type Tone, useToast } from "@/components/ui";
import { api, query } from "@/lib/api";
import { formatDateTime, fromLocalInput, PURPOSE_LABEL, toLocalInput, userName } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Invitation, InvitationStatus, Page, Unit } from "@/lib/types";

const STATUS_TONE: Record<InvitationStatus, Tone> = { active: "green", completed: "blue", cancelled: "slate", expired: "amber" };

export default function InvitationsPage() {
  const { condo, isAdmin } = useSession();
  const toast = useToast();
  const [status, setStatus] = useState<string>("active");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [qr, setQr] = useState<Invitation | null>(null);
  const [creating, setCreating] = useState(false);
  const [cancelling, setCancelling] = useState<Invitation | null>(null);

  const { data, mutate } = useSWR<Page<Invitation>>(
    `/v1/invitations/${query({ condominium: condo.id, status, search, page, ordering: "valid_from" })}`,
    { keepPreviousData: true },
  );

  async function cancel() {
    if (!cancelling) return;
    try {
      await api(`/v1/invitations/${cancelling.id}/cancel/`, { method: "POST" });
      toast("success", "Invitation cancelled.");
      mutate();
    } catch (error) {
      toast("error", (error as Error).message);
    }
    setCancelling(null);
  }

  return (
    <>
      <PageHeader
        title="Invitations"
        description="Visitors pre-registered by residents. The visitor shows the QR code at the gate."
        action={isAdmin && <Button variant="primary" onClick={() => setCreating(true)}>New invitation</Button>}
      />
      <Card>
        <div className="flex flex-wrap gap-2 border-b border-line p-3">
          <SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Visitor, phone or plate" />
          <Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className="sm:w-40" aria-label="Status">
            <option value="">All statuses</option>
            <option value="active">Active</option>
            <option value="completed">Completed</option>
            <option value="expired">Expired</option>
            <option value="cancelled">Cancelled</option>
          </Select>
        </div>
        {!data ? (
          <Loading />
        ) : data.results.length === 0 ? (
          <Empty>No invitations.</Empty>
        ) : (
          <Table>
            <thead>
              <tr><Th>Visitor</Th><Th>Unit · host</Th><Th>Purpose</Th><Th>Valid</Th><Th>Entries</Th><Th>Plate</Th><Th>Status</Th><Th /></tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.results.map((inv) => (
                <tr key={inv.id}>
                  <Td>
                    <div className="font-medium text-ink">{inv.visitor_name}</div>
                    <div className="text-xs text-muted">{inv.visitor_phone}</div>
                  </Td>
                  <Td>
                    <div>{inv.unit_display}</div>
                    <div className="text-xs text-muted">{userName(inv.host_detail)}</div>
                  </Td>
                  <Td>{PURPOSE_LABEL[inv.purpose]}{inv.require_face && <div className="text-xs text-muted">Face check required</div>}</Td>
                  <Td className="whitespace-nowrap tabular-nums text-xs">
                    {formatDateTime(inv.valid_from)}<br />→ {formatDateTime(inv.valid_until)}
                  </Td>
                  <Td className="tabular-nums">{inv.entry_count} / {inv.max_entries}</Td>
                  <Td className="font-mono text-xs">{inv.vehicle_plate || "—"}</Td>
                  <Td><Badge tone={STATUS_TONE[inv.status]}>{inv.status}</Badge></Td>
                  <Td className="whitespace-nowrap text-right">
                    <Button size="sm" variant="ghost" onClick={() => setQr(inv)}>QR</Button>
                    {isAdmin && inv.status === "active" && <Button size="sm" variant="ghost" onClick={() => setCancelling(inv)}>Cancel</Button>}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        {data && <Pagination page={page} count={data.count} onPage={setPage} />}
      </Card>

      <Modal open={!!qr} onClose={() => setQr(null)} title={qr ? `Invitation for ${qr.visitor_name}` : ""}>
        {qr && (
          <div className="space-y-4 text-center">
            <AuthImage path={`/v1/invitations/${qr.id}/qr/`} alt="Invitation QR code" className="mx-auto h-64 w-64" />
            <div className="flex gap-2">
              <Input readOnly value={qr.share_url} onFocus={(e) => e.target.select()} />
              <Button onClick={() => navigator.clipboard?.writeText(qr.share_url).then(() => toast("success", "Link copied."))}>Copy</Button>
            </div>
          </div>
        )}
      </Modal>

      <Modal
        open={!!cancelling}
        onClose={() => setCancelling(null)}
        title="Cancel invitation?"
        footer={<><Button onClick={() => setCancelling(null)}>Keep</Button><Button variant="danger" onClick={cancel}>Cancel invitation</Button></>}
      >
        <p className="text-sm text-body">The QR code for <strong>{cancelling?.visitor_name}</strong> stops working immediately.</p>
      </Modal>

      {creating && <CreateInvitation condoId={condo.id} onClose={() => setCreating(false)} onCreated={() => { setCreating(false); mutate(); }} />}
    </>
  );
}

function CreateInvitation({ condoId, onClose, onCreated }: { condoId: number; onClose: () => void; onCreated: () => void }) {
  const toast = useToast();
  const gates = useGates(condoId);
  const now = new Date();
  const [unit, setUnit] = useState<Unit | null>(null);
  const [form, setForm] = useState({
    visitor_name: "", visitor_phone: "", purpose: "guest", vehicle_plate: "", notes: "",
    valid_from: toLocalInput(now), valid_until: toLocalInput(new Date(now.getTime() + 4 * 3600 * 1000)),
    max_entries: "1", require_face: false, gates: [] as number[],
  });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const set = (key: keyof typeof form, value: unknown) => setForm((f) => ({ ...f, [key]: value }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!unit) return setError(new Error("Choose the unit being visited."));
    setBusy(true);
    setError(null);
    try {
      await api("/v1/invitations/", {
        method: "POST",
        body: {
          ...form, unit: unit.id, max_entries: Number(form.max_entries),
          valid_from: fromLocalInput(form.valid_from), valid_until: fromLocalInput(form.valid_until),
        },
      });
      toast("success", "Invitation created.");
      onCreated();
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="New invitation"
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" busy={busy} type="submit" form="new-invitation">Create</Button></>}
    >
      <form id="new-invitation" onSubmit={submit} className="space-y-4">
        <ErrorNote error={error} />
        <Field label="Unit"><UnitPicker condoId={condoId} value={unit?.id ?? null} onChange={setUnit} /></Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Visitor name"><Input required value={form.visitor_name} onChange={(e) => set("visitor_name", e.target.value)} /></Field>
          <Field label="Mobile number" hint="Singapore numbers: +65 9123 4567"><Input type="tel" value={form.visitor_phone} onChange={(e) => set("visitor_phone", e.target.value)} /></Field>
          <Field label="Purpose">
            <Select value={form.purpose} onChange={(e) => set("purpose", e.target.value)}>
              {Object.entries(PURPOSE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Select>
          </Field>
          <Field label="Vehicle plate (optional)"><Input value={form.vehicle_plate} onChange={(e) => set("vehicle_plate", e.target.value.toUpperCase())} placeholder="SBA1234A" /></Field>
          <Field label="Valid from (SGT)"><Input type="datetime-local" required value={form.valid_from} onChange={(e) => set("valid_from", e.target.value)} /></Field>
          <Field label="Valid until (SGT)"><Input type="datetime-local" required value={form.valid_until} onChange={(e) => set("valid_until", e.target.value)} /></Field>
          <Field label="Max entries"><Input type="number" min={1} max={50} value={form.max_entries} onChange={(e) => set("max_entries", e.target.value)} /></Field>
        </div>
        {gates.data && gates.data.results.length > 1 && (
          <Field label="Gates" hint="Leave all unticked to allow every gate.">
            <div className="flex flex-wrap gap-4 pt-1">
              {gates.data.results.map((g) => (
                <Checkbox key={g.id} label={g.name} checked={form.gates.includes(g.id)}
                  onChange={(e) => set("gates", e.target.checked ? [...form.gates, g.id] : form.gates.filter((id) => id !== g.id))} />
              ))}
            </div>
          </Field>
        )}
        <Checkbox label="Require face check at the gate" checked={form.require_face} onChange={(e) => set("require_face", e.target.checked)} />
        <Field label="Notes"><Textarea rows={2} value={form.notes} onChange={(e) => set("notes", e.target.value)} /></Field>
      </form>
    </Modal>
  );
}
