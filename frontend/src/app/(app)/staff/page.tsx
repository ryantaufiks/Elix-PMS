"use client";

import { useState } from "react";
import useSWR from "swr";

import { ConfirmDialog, EntityModal, remove } from "@/components/forms";
import { AddStaff, EditPerson, SetPassword } from "@/components/people";
import { Icon } from "@/components/icons";
import { Badge, Button, Card, Empty, Loading, PageHeader, Table, Td, Th } from "@/components/ui";
import { query } from "@/lib/api";
import { formatDateTime, ROLE_LABEL, userName } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Page, StaffRow } from "@/lib/types";



const ROLE_OPTIONS = (["security", "staff", "admin"] as const).map((value) => ({ value, label: ROLE_LABEL[value] }));
const ROLE_TONE = { admin: "blue", staff: "green", security: "slate" } as const;

export default function StaffPage() {
  const { condo, isAdmin, me } = useSession();
  const [adding, setAdding] = useState(false);
  const [editingRole, setEditingRole] = useState<StaffRow | null>(null);
  const [editingPerson, setEditingPerson] = useState<StaffRow | null>(null);
  const [password, setPassword] = useState<StaffRow | null>(null);
  const [removing, setRemoving] = useState<StaffRow | null>(null);
  const { data, mutate } = useSWR<Page<StaffRow>>(isAdmin ? `/v1/staff-assignments/${query({ condominium: condo.id, page_size: 200 })}` : null);

  if (!isAdmin) return <Card><Empty>Staff accounts are managed by the site admin.</Empty></Card>;

  return (
    <>
      <PageHeader
        title="Staff"
        description="Officers open gates and handle visitors. Staff also manage residents, vehicles, invitations, bookings and feedback. Site admins also set up the site and manage staff accounts."
        action={<Button variant="primary" onClick={() => setAdding(true)}><Icon name="plus" className="h-4 w-4" /> Add staff</Button>}
      />
      <Card>
        {!data ? <Loading /> : data.results.length === 0 ? <Empty>No staff yet.</Empty> : (
          <Table>
            <thead><tr><Th>Name</Th><Th>Username</Th><Th>Role</Th><Th>Contact</Th><Th>Since</Th><Th /></tr></thead>
            <tbody className="divide-y divide-line">
              {data.results.map((s) => (
                <tr key={s.id}>
                  <Td className="font-medium text-ink">{userName(s.user_detail)}{s.user === me.id && <span className="ml-2"><Badge tone="blue">You</Badge></span>}</Td>
                  <Td>{s.user_detail.username}</Td>
                  <Td><Badge tone={ROLE_TONE[s.role]}>{ROLE_LABEL[s.role]}</Badge></Td>
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
