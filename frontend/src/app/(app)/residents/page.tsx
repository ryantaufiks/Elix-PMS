"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";

import { SearchInput, UnitPicker } from "@/components/bits";
import { ConfirmDialog, EntityModal, FormFields, type FieldDef, initialValues, remove } from "@/components/forms";
import { EditPerson, fieldErrorsOf, personFields, SetPassword } from "@/components/people";
import { Icon } from "@/components/icons";
import { Badge, Button, Card, Empty, ErrorNote, Field, Loading, Modal, PageHeader, Pagination, Select, Table, Td, Th, useToast } from "@/components/ui";
import { api, query, unitSearch } from "@/lib/api";
import { RESIDENT_TYPE_LABEL, userName } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Page, Residency, Unit } from "@/lib/types";

const TYPE_OPTIONS = Object.entries(RESIDENT_TYPE_LABEL).map(([value, label]) => ({ value, label }));

const residencyFields: FieldDef[] = [
  { name: "resident_type", label: "Resident type", type: "select", required: true, options: TYPE_OPTIONS },
  { name: "is_primary_contact", label: "Primary contact for the unit", type: "checkbox", wide: true },
  { name: "receives_intercom_calls", label: "Receives intercom calls", type: "checkbox", wide: true },
  { name: "is_active", label: "Currently living here", type: "checkbox", wide: true },
];

/** Link to the resident APK with its build in the query, so no cache serves an older copy. */
function useApkLink() {
  const [href, setHref] = useState("/downloads/elix-resident.apk");
  useEffect(() => {
    fetch(`/downloads/elix-resident.json?t=${Date.now()}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((info: { version?: string } | null) => { if (info?.version) setHref(`/downloads/elix-resident.apk?v=${info.version}`); })
      .catch(() => {});
  }, []);
  return href;
}

export default function ResidentsPage() {
  const { condo, isManager } = useSession();
  const apk = useApkLink();
  const [search, setSearch] = useState("");
  const [type, setType] = useState("");
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  const [editingPerson, setEditingPerson] = useState<Residency | null>(null);
  const [editingResidency, setEditingResidency] = useState<Residency | null>(null);
  const [password, setPassword] = useState<Residency | null>(null);
  const [removing, setRemoving] = useState<Residency | null>(null);
  const { data, mutate } = useSWR<Page<Residency>>(
    `/v1/residencies/${query({ unit__condominium: condo.id, resident_type: type, search: unitSearch(search), page })}`,
    { keepPreviousData: true },
  );

  return (
    <>
      <PageHeader
        title="Residents"
        description="Who lives in each unit, and who answers intercom calls on the Elix app."
        action={<>
          <a href={apk}><Button><Icon name="smartphone" className="h-4 w-4" /> Resident app (Android)</Button></a>
          {isManager && <Button variant="primary" onClick={() => setAdding(true)}><Icon name="plus" className="h-4 w-4" /> Add resident</Button>}
        </>}
      />
      <Card>
        <div className="flex flex-wrap gap-2 border-b border-line p-4">
          <SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Name or unit number" />
          <Select value={type} onChange={(e) => { setType(e.target.value); setPage(1); }} className="sm:w-44" aria-label="Resident type">
            <option value="">All types</option>
            {TYPE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </Select>
        </div>
        {!data ? <Loading /> : data.results.length === 0 ? <Empty>No residents yet.</Empty> : (
          <Table>
            <thead><tr><Th>Unit</Th><Th>Resident</Th><Th>Type</Th><Th>Contact</Th><Th>Intercom</Th>{isManager && <Th />}</tr></thead>
            <tbody className="divide-y divide-line">
              {data.results.map((r) => (
                <tr key={r.id} className={r.is_active ? undefined : "opacity-60"}>
                  <Td className="whitespace-nowrap font-medium text-ink">{r.unit_display}</Td>
                  <Td>
                    <span className="font-medium text-ink">{userName(r.user_detail)}</span>
                    {r.is_primary_contact && <span className="ml-2"><Badge tone="blue">Primary</Badge></span>}
                    {!r.is_active && <span className="ml-2"><Badge>Moved out</Badge></span>}
                    <div className="text-xs text-muted">{r.user_detail.username}</div>
                  </Td>
                  <Td>{RESIDENT_TYPE_LABEL[r.resident_type]}</Td>
                  <Td className="text-xs">
                    {r.user_detail.phone && <div>{r.user_detail.phone}</div>}
                    {r.user_detail.email && <div className="text-muted">{r.user_detail.email}</div>}
                  </Td>
                  <Td>{r.receives_intercom_calls ? <Badge tone="green">Receives calls</Badge> : <Badge>Muted</Badge>}</Td>
                  {isManager && (
                    <Td className="whitespace-nowrap text-right">
                      <Button size="sm" variant="ghost" onClick={() => setEditingResidency(r)}>Unit role</Button>
                      <Button size="sm" variant="ghost" onClick={() => setEditingPerson(r)}>Profile</Button>
                      <Button size="sm" variant="ghost" onClick={() => setPassword(r)}>Password</Button>
                      <Button size="sm" variant="ghost" onClick={() => setRemoving(r)}>Remove</Button>
                    </Td>
                  )}
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        {data && <Pagination page={page} count={data.count} onPage={setPage} />}
      </Card>

      {adding && <AddResident condoId={condo.id} onClose={() => setAdding(false)} onDone={() => { setAdding(false); mutate(); }} />}
      {editingResidency && (
        <EntityModal title={`${userName(editingResidency.user_detail)} at ${editingResidency.unit_display}`} fields={residencyFields}
          record={editingResidency} endpoint={`/v1/residencies/${editingResidency.id}/`}
          onClose={() => setEditingResidency(null)} onSaved={() => { setEditingResidency(null); mutate(); }} />
      )}
      {editingPerson && <EditPerson userId={editingPerson.user} onClose={() => setEditingPerson(null)} onSaved={() => { setEditingPerson(null); mutate(); }} />}
      {password && <SetPassword userId={password.user} name={userName(password.user_detail)} onClose={() => setPassword(null)} />}
      <ConfirmDialog open={!!removing} title="Remove from unit?" confirmLabel="Remove" onClose={() => setRemoving(null)}
        message={<>Remove <strong>{removing && userName(removing.user_detail)}</strong> from <strong>{removing?.unit_display}</strong>? They stop receiving calls and lose access for this unit. To keep the history, use <em>Unit role</em> and untick &quot;Currently living here&quot;.</>}
        onConfirm={async () => { await remove(`/v1/residencies/${removing!.id}/`); mutate(); }} />
    </>
  );
}

function AddResident({ condoId, onClose, onDone }: { condoId: number; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const fields = personFields(true);
  const [unit, setUnit] = useState<Unit | null>(null);
  const [values, setValues] = useState(() => initialValues(fields, null));
  const [link, setLink] = useState({ resident_type: "owner", is_primary_contact: false, receives_intercom_calls: true });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const errors = fieldErrorsOf(error);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!unit) return setError(new Error("Choose the unit."));
    setBusy(true);
    setError(null);
    try {
      await api("/v1/users/", { method: "POST", body: { ...values, password: values.password || undefined, residency: { unit: unit.id, ...link } } });
      toast("success", "Resident added.");
      onDone();
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <Modal open wide onClose={onClose} title="Add resident" footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" busy={busy} type="submit" form="add-resident">Add resident</Button></>}>
      <form id="add-resident" onSubmit={submit} className="space-y-4">
        <ErrorNote error={Object.keys(errors).length ? null : error} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Unit"><UnitPicker condoId={condoId} value={unit?.id ?? null} onChange={setUnit} /></Field>
          <Field label="Resident type">
            <Select value={link.resident_type} onChange={(e) => setLink((l) => ({ ...l, resident_type: e.target.value }))}>
              {TYPE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
          </Field>
        </div>
        <FormFields fields={fields} values={values} errors={errors} onChange={(n, v) => setValues((s) => ({ ...s, [n]: v }))} />
        <div className="flex flex-wrap gap-6 border-t border-line pt-4 text-sm">
          <label className="flex items-center gap-2"><input type="checkbox" checked={link.is_primary_contact} onChange={(e) => setLink((l) => ({ ...l, is_primary_contact: e.target.checked }))} /> Primary contact</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={link.receives_intercom_calls} onChange={(e) => setLink((l) => ({ ...l, receives_intercom_calls: e.target.checked }))} /> Receives intercom calls</label>
        </div>
      </form>
    </Modal>
  );
}
