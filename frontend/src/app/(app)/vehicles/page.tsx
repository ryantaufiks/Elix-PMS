"use client";

import { useState } from "react";
import useSWR from "swr";

import { SearchInput, UnitPicker } from "@/components/bits";
import { Tabs } from "@/components/forms";
import { Badge, Button, Card, Checkbox, Empty, ErrorNote, Field, Input, Loading, Modal, PageHeader, Pagination, Select, Table, Td, Textarea, Th, type Tone, useToast } from "@/components/ui";
import { api, query } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Page, ParkingPermit, Unit, Vehicle } from "@/lib/types";

const STATUS: Record<Vehicle["status"], { label: string; tone: Tone }> = {
  active: { label: "Active", tone: "green" },
  expiring: { label: "Ends soon", tone: "amber" },
  expired: { label: "Expired", tone: "red" },
  upcoming: { label: "Not started", tone: "blue" },
  inactive: { label: "Inactive", tone: "slate" },
};

type Tab = "all" | "resident" | "season" | "temporary" | "expiring" | "expired" | "payments";

const PERMIT_TONE: Record<ParkingPermit["status"], Tone> = { pending_payment: "amber", paid: "green", expired: "slate", cancelled: "slate" };

/** Season parking bought in the resident app: who paid, for which plate and period. */
function Payments({ condoId, search }: { condoId: number; search: string }) {
  const [page, setPage] = useState(1);
  const { data } = useSWR<Page<ParkingPermit>>(`/v1/parking-permits/${query({ condominium: condoId, search, page })}`, { keepPreviousData: true });
  if (!data) return <Loading />;
  if (data.results.length === 0) {
    return <Empty icon="car" title="No season parking bought yet">Residents buy season parking in the app once it is on sale (Site settings → Season parking).</Empty>;
  }
  return (
    <>
      <Table>
        <thead><tr><Th>Bought</Th><Th>Plate</Th><Th>Unit</Th><Th>Period</Th><Th>Amount</Th><Th>Status</Th></tr></thead>
        <tbody className="divide-y divide-line">
          {data.results.map((p) => (
            <tr key={p.id}>
              <Td className="whitespace-nowrap tabular-nums">{formatDateTime(p.created_at)}<div className="text-xs text-muted">{p.bought_by}</div></Td>
              <Td className="font-mono font-medium text-ink">{p.plate_number}{p.holder_name && <div className="font-sans text-xs font-normal text-muted">{p.holder_name}</div>}</Td>
              <Td>{p.unit_display}</Td>
              <Td className="whitespace-nowrap">{formatDate(p.starts_on)} – {formatDate(p.ends_on)}<div className="text-xs text-muted">{p.months} month{p.months === 1 ? "" : "s"}</div></Td>
              <Td className="whitespace-nowrap tabular-nums">{p.currency} {p.amount}</Td>
              <Td><Badge tone={PERMIT_TONE[p.status]}>{p.status_display}</Badge></Td>
            </tr>
          ))}
        </tbody>
      </Table>
      <Pagination page={page} count={data.count} onPage={setPage} />
    </>
  );
}

/** "1 Dec 2026 – 31 Mar 2027", "Until 31 Mar 2027" or "No end date". */
function validity(v: Vehicle) {
  if (v.valid_from && v.valid_until) return `${formatDate(v.valid_from)} – ${formatDate(v.valid_until)}`;
  if (v.valid_until) return `Until ${formatDate(v.valid_until)}`;
  if (v.valid_from) return `From ${formatDate(v.valid_from)}`;
  return "No end date";
}

export default function VehiclesPage() {
  const { condo, isManager } = useSession();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [tab, setTab] = useState<Tab>("all");
  const [editing, setEditing] = useState<Vehicle | "new" | null>(null);
  const filters = tab === "expiring" || tab === "expired" ? { status: tab } : tab === "all" ? {} : { kind: tab };
  const { data, mutate } = useSWR<Page<Vehicle>>(tab === "payments" ? null : `/v1/vehicles/${query({ condominium: condo.id, search, page, ...filters })}`, { keepPreviousData: true });
  const expiring = useSWR<Page<Vehicle>>(`/v1/vehicles/${query({ condominium: condo.id, status: "expiring", page_size: 1 })}`);

  return (
    <>
      <PageHeader
        title="Vehicles"
        description="Plates that open LPR gates: residents' cars, season parking and temporary passes. A plate opens only between its start and end dates."
        action={isManager && <Button variant="primary" onClick={() => setEditing("new")}>Add vehicle</Button>}
      />
      <Card>
        <Tabs active={tab} onChange={(t) => { setTab(t); setPage(1); }} tabs={[
          { key: "all", label: "All" }, { key: "resident", label: "Residents" }, { key: "season", label: "Season parking" },
          { key: "temporary", label: "Temporary" }, { key: "expiring", label: "Ending in 7 days", count: expiring.data?.count }, { key: "expired", label: "Expired" },
          { key: "payments", label: "Season parking payments" },
        ]} />
        <div className="border-b border-line p-3">
          <SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Plate, make, model or holder" />
        </div>
        {tab === "payments" ? (
          <Payments condoId={condo.id} search={search} />
        ) : !data ? (
          <Loading />
        ) : data.results.length === 0 ? (
          <Empty icon="car" title="No vehicles registered" action={isManager && <Button variant="primary" size="sm" onClick={() => setEditing("new")}>Add vehicle</Button>}>Plates listed here open LPR gates automatically for residents.</Empty>
        ) : (
          <Table>
            <thead><tr><Th>Plate</Th><Th>Unit</Th><Th>Vehicle</Th><Th>Type</Th><Th>Valid</Th><Th>Status</Th><Th /></tr></thead>
            <tbody className="divide-y divide-line">
              {data.results.map((v) => (
                <tr key={v.id}>
                  <Td className="font-mono font-medium text-ink">{v.plate_number}</Td>
                  <Td>
                    {v.unit_display}
                    {v.holder_name && <div className="text-xs text-muted">{v.holder_name}</div>}
                  </Td>
                  <Td>{[v.colour, v.make, v.model].filter(Boolean).join(" ") || "—"}</Td>
                  <Td className="whitespace-nowrap">{v.kind_display}</Td>
                  <Td className="whitespace-nowrap">{validity(v)}</Td>
                  <Td><Badge tone={STATUS[v.status].tone}>{STATUS[v.status].label}</Badge></Td>
                  <Td className="text-right">{isManager && <Button size="sm" variant="ghost" onClick={() => setEditing(v)}>Edit</Button>}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        {data && tab !== "payments" && <Pagination page={page} count={data.count} onPage={setPage} />}
      </Card>
      {editing && (
        <VehicleForm condoId={condo.id} vehicle={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); mutate(); }} />
      )}
    </>
  );
}

function VehicleForm({ condoId, vehicle, onClose, onSaved }: { condoId: number; vehicle: Vehicle | null; onClose: () => void; onSaved: () => void }) {
  const toast = useToast();
  const [unitId, setUnitId] = useState<number | null>(vehicle?.unit ?? null);
  const [form, setForm] = useState({
    plate_number: vehicle?.plate_number ?? "", make: vehicle?.make ?? "", model: vehicle?.model ?? "",
    colour: vehicle?.colour ?? "", notes: vehicle?.notes ?? "", is_active: vehicle?.is_active ?? true,
    kind: vehicle?.kind ?? "resident", holder_name: vehicle?.holder_name ?? "",
    valid_from: vehicle?.valid_from ?? "", valid_until: vehicle?.valid_until ?? "",
  });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const set = (key: keyof typeof form, value: unknown) => setForm((f) => ({ ...f, [key]: value }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!unitId) return setError(new Error("Choose the resident's unit."));
    setBusy(true);
    setError(null);
    try {
      await api(vehicle ? `/v1/vehicles/${vehicle.id}/` : "/v1/vehicles/", {
        method: vehicle ? "PATCH" : "POST",
        body: { ...form, unit: unitId, valid_from: form.valid_from || null, valid_until: form.valid_until || null },
      });
      toast("success", vehicle ? "Vehicle updated." : "Vehicle added.");
      onSaved();
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={vehicle ? `Edit ${vehicle.plate_number}` : "Add vehicle"}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" busy={busy} type="submit" form="vehicle-form">Save</Button></>}
    >
      <form id="vehicle-form" onSubmit={submit} className="space-y-4">
        <ErrorNote error={error} />
        <Field label="Unit">
          <UnitPicker condoId={condoId} value={unitId} initialLabel={vehicle?.unit_display} onChange={(u: Unit | null) => setUnitId(u?.id ?? null)} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Plate number" hint="Spaces are removed automatically.">
            <Input required value={form.plate_number} onChange={(e) => set("plate_number", e.target.value.toUpperCase())} placeholder="SBA1234A" />
          </Field>
          <Field label="Colour"><Input value={form.colour} onChange={(e) => set("colour", e.target.value)} /></Field>
          <Field label="Make"><Input value={form.make} onChange={(e) => set("make", e.target.value)} placeholder="Toyota" /></Field>
          <Field label="Model"><Input value={form.model} onChange={(e) => set("model", e.target.value)} placeholder="Corolla Altis" /></Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Type">
            <Select value={form.kind} onChange={(e) => set("kind", e.target.value)}>
              <option value="resident">Resident</option>
              <option value="season">Season parking</option>
              <option value="temporary">Temporary</option>
            </Select>
          </Field>
          <Field label="Holder name" hint={form.kind === "resident" ? "Optional: when the driver is not the unit's resident." : "Who the pass is for."}>
            <Input value={form.holder_name} onChange={(e) => set("holder_name", e.target.value)} />
          </Field>
          <Field label="Valid from" hint="Leave empty to start today.">
            <Input type="date" value={form.valid_from} onChange={(e) => set("valid_from", e.target.value)} />
          </Field>
          <Field label="Valid until" hint={form.kind === "resident" ? "Leave empty for no end date." : "Required: the last day the plate opens the gate."}>
            <Input type="date" required={form.kind !== "resident"} value={form.valid_until} min={form.valid_from || undefined}
              onChange={(e) => set("valid_until", e.target.value)} />
          </Field>
        </div>
        <Field label="Notes"><Textarea rows={2} value={form.notes} onChange={(e) => set("notes", e.target.value)} /></Field>
        <Checkbox label="Active (can open LPR gates)" checked={form.is_active} onChange={(e) => set("is_active", e.target.checked)} />
      </form>
    </Modal>
  );
}
