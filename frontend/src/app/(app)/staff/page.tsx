"use client";

import { useState } from "react";
import useSWR from "swr";

import { ConfirmDialog, EntityModal, FormFields, initialValues, remove } from "@/components/forms";
import { EditPerson, fieldErrorsOf, personFields, SetPassword } from "@/components/people";
import { Icon } from "@/components/icons";
import { Badge, Button, Card, Empty, ErrorNote, Field, Loading, Modal, PageHeader, Select, Table, Td, Th, useToast } from "@/components/ui";
import { api, query } from "@/lib/api";
import { formatDateTime, userName } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Page, StaffRow } from "@/lib/types";



const ROLE_OPTIONS = [{ value: "security", label: "Security guard" }, { value: "admin", label: "Condo admin" }];

export default function StaffPage() {
  const { condo, isAdmin, me } = useSession();
  const [adding, setAdding] = useState(false);
  const [editingRole, setEditingRole] = useState<StaffRow | null>(null);
  const [editingPerson, setEditingPerson] = useState<StaffRow | null>(null);
  const [password, setPassword] = useState<StaffRow | null>(null);
  const [removing, setRemoving] = useState<StaffRow | null>(null);
  const { data, mutate } = useSWR<Page<StaffRow>>(isAdmin ? `/v1/staff-assignments/${query({ condominium: condo.id, page_size: 200 })}` : null);

  if (!isAdmin) return <Card><Empty>Staff accounts are managed by the condo admin.</Empty></Card>;

  return (
    <>
      <PageHeader
        title="Staff"
        description="Security guards use the dashboard and the guardhouse intercom; condo admins also manage the site."
        action={<Button variant="primary" onClick={() => setAdding(true)}><Icon name="plus" className="h-4 w-4" /> Add staff</Button>}
      />
      <Card>
        {!data ? <Loading /> : data.results.length === 0 ? <Empty>No staff yet.</Empty> : (
          <Table>
            <thead><tr><Th>Name</Th><Th>Username</Th><Th>Role</Th><Th>Contact</Th><Th>Since</Th><Th /></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {data.results.map((s) => (
                <tr key={s.id}>
                  <Td className="font-medium text-ink">{userName(s.user_detail)}{s.user === me.id && <span className="ml-2"><Badge tone="blue">You</Badge></span>}</Td>
                  <Td>{s.user_detail.username}</Td>
                  <Td>{s.role === "admin" ? <Badge tone="blue">Condo admin</Badge> : <Badge>Security</Badge>}</Td>
                  <Td className="text-xs">{s.user_detail.phone}<div className="text-muted">{s.user_detail.email}</div></Td>
                  <Td className="whitespace-nowrap">{formatDateTime(s.created_at)}</Td>
                  <Td className="whitespace-nowrap text-right">
                    <Button size="sm" variant="ghost" onClick={() => setEditingRole(s)}>Role</Button>
                    <Button size="sm" variant="ghost" onClick={() => setEditingPerson(s)}>Profile</Button>
                    <Button size="sm" variant="ghost" onClick={() => setPassword(s)}>Password</Button>
                    {s.user !== me.id && <Button size="sm" variant="ghost" onClick={() => setRemoving(s)}>Remove</Button>}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
      {adding && <AddStaff condoId={condo.id} onClose={() => setAdding(false)} onDone={() => { setAdding(false); mutate(); }} />}
      {editingRole && (
        <EntityModal title={`Role of ${userName(editingRole.user_detail)}`} fields={[{ name: "role", label: "Role", type: "select", required: true, options: ROLE_OPTIONS, wide: true }]}
          record={editingRole} endpoint={`/v1/staff-assignments/${editingRole.id}/`} onClose={() => setEditingRole(null)} onSaved={() => { setEditingRole(null); mutate(); }} />
      )}
      {editingPerson && <EditPerson userId={editingPerson.user} onClose={() => setEditingPerson(null)} onSaved={() => { setEditingPerson(null); mutate(); }} />}
      {password && <SetPassword userId={password.user} name={userName(password.user_detail)} onClose={() => setPassword(null)} />}
      <ConfirmDialog open={!!removing} title="Remove from staff?" confirmLabel="Remove" onClose={() => setRemoving(null)}
        message={<><strong>{removing && userName(removing.user_detail)}</strong> loses dashboard access for {condo.name} immediately.</>}
        onConfirm={async () => { await remove(`/v1/staff-assignments/${removing!.id}/`); mutate(); }} />
    </>
  );
}

function AddStaff({ condoId, onClose, onDone }: { condoId: number; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const fields = personFields(true).map((f) => (f.name === "password" ? { ...f, required: true, hint: "At least 8 characters. Staff sign in to the dashboard with it." } : f));
  const [values, setValues] = useState(() => initialValues(fields, null));
  const [role, setRole] = useState("security");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const errors = fieldErrorsOf(error);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/v1/users/", { method: "POST", body: { ...values, staff: { condominium: condoId, role } } });
      toast("success", "Staff account created.");
      onDone();
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <Modal open wide onClose={onClose} title="Add staff" footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" busy={busy} type="submit" form="add-staff">Create account</Button></>}>
      <form id="add-staff" onSubmit={submit} className="space-y-4">
        <ErrorNote error={Object.keys(errors).length ? null : error} />
        <Field label="Role">
          <Select value={role} onChange={(e) => setRole(e.target.value)}>
            {ROLE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </Select>
        </Field>
        <FormFields fields={fields} values={values} errors={errors} onChange={(n, v) => setValues((s) => ({ ...s, [n]: v }))} />
      </form>
    </Modal>
  );
}
