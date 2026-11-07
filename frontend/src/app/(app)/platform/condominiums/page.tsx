"use client";

import { useState } from "react";
import useSWR from "swr";

import { EntityModal } from "@/components/forms";
import { Icon } from "@/components/icons";
import { Badge, Button, Card, Empty, Loading, PageHeader, Table, Td, Th } from "@/components/ui";
import { condoDefaults, condoFields } from "@/lib/fields";
import { useSession } from "@/lib/session";
import type { Condominium, Page } from "@/lib/types";

export default function CondominiumsPage() {
  const { me, condo: current, selectCondo, reload } = useSession();
  const [editing, setEditing] = useState<Condominium | "new" | null>(null);
  const { data, mutate } = useSWR<Page<Condominium>>(me.is_superuser ? "/v1/condominiums/?page_size=200" : null);

  if (!me.is_superuser) return <Card><Empty>Only the platform administrator manages condominiums.</Empty></Card>;

  return (
    <>
      <PageHeader
        title="Condominiums"
        description="Every site on this platform. Each site has its own staff, residents, gates and devices."
        action={<Button variant="primary" onClick={() => setEditing("new")}><Icon name="plus" className="h-4 w-4" /> Add condominium</Button>}
      />
      <Card>
        {!data ? <Loading /> : data.results.length === 0 ? <Empty>No condominiums.</Empty> : (
          <Table>
            <thead><tr><Th>Name</Th><Th>Code</Th><Th>Postal code</Th><Th>LPR</Th><Th>Status</Th><Th /></tr></thead>
            <tbody className="divide-y divide-line">
              {data.results.map((c) => (
                <tr key={c.id}>
                  <Td className="font-medium text-ink">{c.name}{c.id === current.id && <span className="ml-2"><Badge tone="blue">Selected</Badge></span>}</Td>
                  <Td className="font-mono text-xs">{c.code}</Td>
                  <Td>{c.postal_code || "—"}</Td>
                  <Td>{c.lpr_enabled ? <Badge tone="green">On</Badge> : <Badge>Off</Badge>}</Td>
                  <Td>{c.is_active ? <Badge tone="green">Active</Badge> : <Badge>Inactive</Badge>}</Td>
                  <Td className="whitespace-nowrap text-right">
                    {c.is_active && c.id !== current.id && <Button size="sm" variant="ghost" onClick={() => selectCondo(c.id)}>Switch to</Button>}
                    <Button size="sm" variant="ghost" onClick={() => setEditing(c)}>Edit</Button>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
      {editing && (
        <EntityModal<Condominium> wide title={editing === "new" ? "Add condominium" : `Edit ${editing.name}`}
          fields={condoFields({ superuser: true, creating: editing === "new" })}
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
