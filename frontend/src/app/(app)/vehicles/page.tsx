"use client";

import { useState } from "react";
import useSWR from "swr";

import { SearchInput, UnitPicker } from "@/components/bits";
import { Badge, Button, Card, Checkbox, Empty, ErrorNote, Field, Input, Loading, Modal, PageHeader, Pagination, Table, Td, Textarea, Th, useToast } from "@/components/ui";
import { api, query } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { Page, Unit, Vehicle } from "@/lib/types";

export default function VehiclesPage() {
  const { condo, isAdmin } = useSession();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Vehicle | "new" | null>(null);
  const { data, mutate } = useSWR<Page<Vehicle>>(`/v1/vehicles/${query({ condominium: condo.id, search, page })}`, { keepPreviousData: true });

  return (
    <>
      <PageHeader
        title="Vehicles"
        description="Resident vehicles. Plates listed here can open LPR gates set to auto-open for residents."
        action={isAdmin && <Button variant="primary" onClick={() => setEditing("new")}>Add vehicle</Button>}
      />
      <Card>
        <div className="border-b border-line p-3">
          <SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Plate, make or model" />
        </div>
        {!data ? (
          <Loading />
        ) : data.results.length === 0 ? (
          <Empty>No vehicles registered.</Empty>
        ) : (
          <Table>
            <thead><tr><Th>Plate</Th><Th>Unit</Th><Th>Vehicle</Th><Th>Status</Th><Th /></tr></thead>
            <tbody className="divide-y divide-line">
              {data.results.map((v) => (
                <tr key={v.id}>
                  <Td className="font-mono font-medium text-ink">{v.plate_number}</Td>
                  <Td>{v.unit_display}</Td>
                  <Td>{[v.colour, v.make, v.model].filter(Boolean).join(" ") || "—"}</Td>
                  <Td>{v.is_active ? <Badge tone="green">Active</Badge> : <Badge>Inactive</Badge>}</Td>
                  <Td className="text-right">{isAdmin && <Button size="sm" variant="ghost" onClick={() => setEditing(v)}>Edit</Button>}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        {data && <Pagination page={page} count={data.count} onPage={setPage} />}
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
        body: { ...form, unit: unitId },
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
        <Field label="Notes"><Textarea rows={2} value={form.notes} onChange={(e) => set("notes", e.target.value)} /></Field>
        <Checkbox label="Active (can open LPR gates)" checked={form.is_active} onChange={(e) => set("is_active", e.target.checked)} />
      </form>
    </Modal>
  );
}
