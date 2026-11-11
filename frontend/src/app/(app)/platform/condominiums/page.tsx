"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";

import { EntityModal } from "@/components/forms";
import { AddStaff } from "@/components/people";
import { STATUS } from "@/components/PlanSummary";
import { Icon } from "@/components/icons";
import { Badge, Button, Card, Empty, Loading, PageHeader, Table, Td, Th } from "@/components/ui";
import { condoDefaults, condoFields } from "@/lib/fields";
import { userName } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Condominium, Page, Plan, StaffRow } from "@/lib/types";

export default function CondominiumsPage() {
  const { me, condo: current, selectCondo, reload } = useSession();
  const [editing, setEditing] = useState<Condominium | "new" | null>(null);
  const { data, mutate } = useSWR<Page<Condominium>>(me.is_superuser ? "/v1/condominiums/?page_size=200" : null);
  const { data: plans } = useSWR<Plan[]>(me.is_superuser ? "/v1/plans/" : null);
  const { data: admins, mutate: reloadAdmins } = useSWR<Page<StaffRow>>(me.is_superuser ? "/v1/staff-assignments/?role=admin&page_size=200" : null);
  const [addingAdmin, setAddingAdmin] = useState<Condominium | null>(null);
  const adminsOf = (id: number) => (admins?.results ?? []).filter((a) => a.condominium === id);

  if (!me.is_superuser) return <Card><Empty>Only the platform administrator manages condominiums.</Empty></Card>;

  return (
    <>
      <PageHeader
        title="Condominiums"
        description="Every site on this platform, its plan and subscription. Each site has its own staff, residents, gates and devices."
        action={<Button variant="primary" onClick={() => setEditing("new")}><Icon name="plus" className="h-4 w-4" /> Add condominium</Button>}
      />
      <Card>
        {!data ? <Loading /> : data.results.length === 0 ? <Empty>No condominiums.</Empty> : (
          <Table>
            <thead><tr><Th>Site</Th><Th>Plan</Th><Th>Subscription</Th><Th>Site admins</Th><Th>Status</Th><Th /></tr></thead>
            <tbody className="divide-y divide-line">
              {data.results.map((c) => (
                <tr key={c.id}>
                  <Td className="font-medium text-ink">
                    {c.name}{c.id === current.id && <span className="ml-2"><Badge tone="blue">Selected</Badge></span>}
                    <div className="font-mono text-xs font-normal text-muted">{c.code}</div>
                  </Td>
                  <Td>{c.plan_name || "—"}</Td>
                  <Td>{c.subscription_status ? <Badge tone={STATUS[c.subscription_status].tone}>{STATUS[c.subscription_status].label}</Badge> : "—"}</Td>
                  <Td>
                    {adminsOf(c.id).length
                      ? <span className="text-sm text-ink">{adminsOf(c.id).map((a) => userName(a.user_detail)).join(", ")}</span>
                      : <Badge tone="amber">None yet</Badge>}
                  </Td>
                  <Td>{c.is_active ? <Badge tone="green">Active</Badge> : <Badge>Inactive</Badge>}</Td>
                  <Td className="whitespace-nowrap text-right">
                    {c.is_active && c.id !== current.id && <Button size="sm" variant="ghost" onClick={() => selectCondo(c.id)}>Switch to</Button>}
                    <Button size="sm" variant="ghost" onClick={() => setAddingAdmin(c)}>Add site admin</Button>
                    <Link href={`/platform/subscription/?site=${c.id}`}><Button size="sm" variant="ghost">Subscription</Button></Link>
                    <Button size="sm" variant="ghost" onClick={() => setEditing(c)}>Edit</Button>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
      {addingAdmin && (
        <AddStaff condoId={addingAdmin.id} role="admin" title={`Add site admin · ${addingAdmin.name}`}
          onClose={() => setAddingAdmin(null)} onDone={() => { setAddingAdmin(null); reloadAdmins(); }} />
      )}
      {editing && (
        <EntityModal<Condominium> wide title={editing === "new" ? "Add condominium" : `Edit ${editing.name}`}
          fields={condoFields({ superuser: true, creating: editing === "new", plans: (plans ?? []).filter((p) => p.is_active) })}
          record={editing === "new" ? null : editing} defaults={condoDefaults}
          endpoint={editing === "new" ? "/v1/condominiums/" : `/v1/condominiums/${editing.id}/`}
          onClose={() => setEditing(null)}
          onSaved={async (saved) => {
            setEditing(null);
            mutate();
            await reload();
            if (editing === "new") selectCondo(saved.id);
          }} />
      )}
    </>
  );
}
