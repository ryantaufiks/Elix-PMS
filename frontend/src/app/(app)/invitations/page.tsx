"use client";

import { useState } from "react";
import useSWR from "swr";

import { AuthImage, SearchInput, UnitPicker, useGates } from "@/components/bits";
import { Tabs, WeekdayPicker } from "@/components/forms";
import { Badge, Button, Card, Checkbox, Empty, ErrorNote, Field, Input, Loading, Modal, PageHeader, Pagination, Select, Table, Td, Textarea, Th, type Tone, useToast } from "@/components/ui";
import { api, query } from "@/lib/api";
import { formatDateTime, fromLocalInput, PURPOSE_LABEL, toLocalInput, userName } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Invitation, InvitationStatus, Page, Unit } from "@/lib/types";

const STATUS_TONE: Record<InvitationStatus, Tone> = { active: "green", completed: "blue", cancelled: "slate", expired: "amber" };

export default function InvitationsPage() {
  const { condo, isManager } = useSession();
  const toast = useToast();
  const [status, setStatus] = useState<string>("active");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [qr, setQr] = useState<Invitation | null>(null);
  const [creating, setCreating] = useState(false);
  const [vendorForm, setVendorForm] = useState(false);
  const [cancelling, setCancelling] = useState<Invitation | null>(null);
  const [tab, setTab] = useState<"all" | "vendor">("all");

  const { data, mutate } = useSWR<Page<Invitation>>(
    `/v1/invitations/${query({ condominium: condo.id, status, search, page, ordering: "valid_from", ...(tab === "vendor" ? { vendor: 1 } : {}) })}`,
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
        description="Visitors pre-registered by residents, and vendor passes for contractors and the MCST's vendors. The visitor shows the QR code at the gate."
        action={isManager && (
          <>
            <Button onClick={() => setVendorForm(true)}>New vendor pass</Button>
            <Button variant="primary" onClick={() => setCreating(true)}>New invitation</Button>
          </>
        )}
      />
      <Card>
        <Tabs active={tab} onChange={(t) => { setTab(t); setPage(1); }}
          tabs={[{ key: "all", label: "All invitations" }, { key: "vendor", label: "Vendor passes" }]} />
        <div className="flex flex-wrap gap-2 border-b border-line p-3">
          <SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Visitor, company, phone or plate" />
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
          <Empty icon="ticket" title="No invitations here" action={isManager && <Button variant="primary" size="sm" onClick={() => setCreating(true)}>New invitation</Button>}>Residents invite visitors from the app; staff can create one here. Try another status filter to see older ones.</Empty>
        ) : (
          <Table>
            <thead>
              <tr><Th>Visitor</Th><Th>Unit · host</Th><Th>Purpose</Th><Th>Valid</Th><Th>Entries</Th><Th>Plate</Th><Th>Status</Th><Th /></tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.results.map((inv) => (
                <tr key={inv.id}>
                  <Td>
                    <div className="font-medium text-ink">{inv.company || inv.visitor_name}</div>
                    <div className="text-xs text-muted">{[inv.company ? inv.visitor_name : "", inv.visitor_phone].filter(Boolean).join(" · ")}</div>
                  </Td>
                  <Td>
                    <div>{inv.unit_display}</div>
                    <div className="text-xs text-muted">{userName(inv.host_detail)}</div>
                  </Td>
                  <Td>{PURPOSE_LABEL[inv.purpose]}{inv.require_face && <div className="text-xs text-muted">Face check required</div>}</Td>
                  <Td className="whitespace-nowrap tabular-nums text-xs">
                    {formatDateTime(inv.valid_from)}<br />→ {formatDateTime(inv.valid_until)}
                    {inv.schedule && <div className="mt-1 font-medium text-ink">{inv.schedule}</div>}
                  </Td>
                  <Td className="tabular-nums">{inv.entry_count} / {inv.max_entries || "∞"}</Td>
                  <Td className="font-mono text-xs">{inv.vehicle_plate || "—"}</Td>
                  <Td><Badge tone={STATUS_TONE[inv.status]}>{inv.status}</Badge></Td>
                  <Td className="whitespace-nowrap text-right">
                    <Button size="sm" variant="ghost" onClick={() => setQr(inv)}>QR</Button>
                    {isManager && inv.status === "active" && <Button size="sm" variant="ghost" onClick={() => setCancelling(inv)}>Cancel</Button>}
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

      {vendorForm && <CreateVendorPass condoId={condo.id} onClose={() => setVendorForm(false)} onCreated={(inv) => { setVendorForm(false); setTab("vendor"); mutate(); setQr(inv); }} />}
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

/** A company's recurring access: dates, days of the week and hours each day, for the MCST's vendors
    (recorded against the management office) or a resident's contractor (against the unit). */
function CreateVendorPass({ condoId, onClose, onCreated }: { condoId: number; onClose: () => void; onCreated: (inv: Invitation) => void }) {
  const toast = useToast();
  const today = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Singapore" });
  const [forOffice, setForOffice] = useState(true);
  const [unit, setUnit] = useState<Unit | null>(null);
  const [form, setForm] = useState({
    company: "", visitor_name: "", visitor_phone: "", purpose: "contractor", vehicle_plate: "", notes: "",
    from: today, to: today, weekdays: [0, 1, 2, 3, 4] as number[], daily_from: "09:00", daily_until: "17:00",
  });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const set = (key: keyof typeof form, value: unknown) => setForm((f) => ({ ...f, [key]: value }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!forOffice && !unit) return setError(new Error("Choose the unit the contractor works for."));
    setBusy(true);
    setError(null);
    try {
      const target = forOffice ? (await api<Unit>(`/v1/units/office/?condominium=${condoId}`)).id : unit!.id;
      const { from, to, ...rest } = form;
      const created = await api<Invitation>("/v1/invitations/", {
        method: "POST",
        body: {
          ...rest, unit: target, visitor_name: form.visitor_name.trim() || form.company.trim(), max_entries: 0,
          valid_from: `${from}T00:00:00+08:00`, valid_until: `${to}T23:59:00+08:00`,
          daily_from: form.daily_from || null, daily_until: form.daily_until || null,
        },
      });
      toast("success", "Vendor pass created. Share its link or QR with the company.");
      onCreated(created);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} title="New vendor pass" wide
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" busy={busy} type="submit" form="new-vendor-pass">Create</Button></>}>
      <form id="new-vendor-pass" onSubmit={submit} className="space-y-4">
        <ErrorNote error={error} />
        <div className="flex flex-wrap gap-4">
          <label className="flex items-center gap-2 text-sm text-body"><input type="radio" checked={forOffice} onChange={() => setForOffice(true)} /> For the management office (MCST vendor)</label>
          <label className="flex items-center gap-2 text-sm text-body"><input type="radio" checked={!forOffice} onChange={() => setForOffice(false)} /> For a unit (resident&apos;s contractor)</label>
        </div>
        {!forOffice && <Field label="Unit"><UnitPicker condoId={condoId} value={unit?.id ?? null} onChange={setUnit} /></Field>}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Company"><Input required value={form.company} onChange={(e) => set("company", e.target.value)} placeholder="e.g. Acme Lift Services" /></Field>
          <Field label="Contact person (optional)"><Input value={form.visitor_name} onChange={(e) => set("visitor_name", e.target.value)} /></Field>
          <Field label="Mobile number (optional)"><Input type="tel" value={form.visitor_phone} onChange={(e) => set("visitor_phone", e.target.value)} /></Field>
          <Field label="Purpose">
            <Select value={form.purpose} onChange={(e) => set("purpose", e.target.value)}>
              {Object.entries(PURPOSE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Select>
          </Field>
          <Field label="From"><Input type="date" required value={form.from} min={today} onChange={(e) => set("from", e.target.value)} /></Field>
          <Field label="To"><Input type="date" required value={form.to} min={form.from} onChange={(e) => set("to", e.target.value)} /></Field>
        </div>
        <Field label="Days" hint="None ticked: every day."><WeekdayPicker value={form.weekdays} onChange={(days) => set("weekdays", days)} /></Field>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Each day from"><Input type="time" value={form.daily_from} onChange={(e) => set("daily_from", e.target.value)} /></Field>
          <Field label="Each day until" hint="Overstay alert after this."><Input type="time" value={form.daily_until} onChange={(e) => set("daily_until", e.target.value)} /></Field>
          <Field label="Vehicle plate (optional)"><Input value={form.vehicle_plate} onChange={(e) => set("vehicle_plate", e.target.value.toUpperCase())} placeholder="GBA1234A" /></Field>
        </div>
        <p className="text-xs text-muted">One pass for the whole team: unlimited entries within these days and hours. Contractors also follow the site&apos;s working hours when they are on.</p>
        <Field label="Notes"><Textarea rows={2} value={form.notes} onChange={(e) => set("notes", e.target.value)} placeholder="e.g. Monthly lift servicing, Block A and B" /></Field>
      </form>
    </Modal>
  );
}
