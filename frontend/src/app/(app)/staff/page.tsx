"use client";

import { useState } from "react";
import useSWR from "swr";

import { ConfirmDialog, EntityModal, remove } from "@/components/forms";
import { AddStaff, EditPerson, SetPassword } from "@/components/people";
import { Icon } from "@/components/icons";
import { Badge, Button, Card, Empty, Loading, PageHeader, RowMenu, Table, Td, Th } from "@/components/ui";
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
        {!data ? <Loading /> : data.results.length === 0 ? <Empty icon="shield" title="No staff yet" action={<Button variant="primary" size="sm" onClick={() => setAdding(true)}>Add staff</Button>}>Officers open gates and handle visitors; staff manage residents and bookings.</Empty> : (
          <Table>
            <thead><tr><Th>Name</Th><Th>Username</Th><Th>Role</Th><Th>Contact</Th><Th>Since</Th><Th /></tr></thead>
            <tbody className="divide-y divide-line">
              {data.results.map((s) => (
                <tr key={s.id}>
                  <Td label="Name" className="font-medium text-ink">{userName(s.user_detail)}{s.user === me.id && <span className="ml-2"><Badge tone="blue">You</Badge></span>}</Td>
                  <Td label="Username">{s.user_detail.username}</Td>
                  <Td label="Role"><Badge tone={ROLE_TONE[s.role]}>{ROLE_LABEL[s.role]}</Badge></Td>
                  <Td label="Contact" className="text-xs">{s.user_detail.phone}<div className="text-muted">{s.user_detail.email}</div></Td>
                  <Td label="Since" className="whitespace-nowrap">{formatDateTime(s.created_at)}</Td>
                  <Td className="whitespace-nowrap text-right">
                    <RowMenu primary={{ label: "Profile", onClick: () => setEditingPerson(s) }} items={[
                      { label: "Change role", onClick: () => setEditingRole(s) },
                      { label: "Set password", onClick: () => setPassword(s) },
                      { label: "Remove from staff", onClick: () => setRemoving(s), danger: true, hidden: s.user === me.id },
                    ]} />
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
