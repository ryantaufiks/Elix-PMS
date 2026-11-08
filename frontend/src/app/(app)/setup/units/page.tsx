"use client";

import { useState } from "react";
import useSWR from "swr";

import { SearchInput } from "@/components/bits";
import { ConfirmDialog, EntityModal, type FieldDef, remove } from "@/components/forms";
import { Icon } from "@/components/icons";
import { Badge, Button, Card, CardHeader, cx, Empty, ErrorNote, Field, Input, Loading, Modal, PageHeader, Pagination, Select, Table, Td, Th, useToast } from "@/components/ui";
import { api, query, unitSearch } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { Block, Page, Unit } from "@/lib/types";

const blockFields: FieldDef[] = [{ name: "name", label: "Block name", required: true, placeholder: "e.g. Block 12 or Tower A", wide: true }];

export default function UnitsSetupPage() {
  const { condo, isAdmin } = useSession();
  const [blockFilter, setBlockFilter] = useState<number | "none" | "">("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [editingBlock, setEditingBlock] = useState<Block | "new" | null>(null);
  const [deletingBlock, setDeletingBlock] = useState<Block | null>(null);
  const [editingUnit, setEditingUnit] = useState<Unit | "new" | null>(null);
  const [deletingUnit, setDeletingUnit] = useState<Unit | null>(null);
  const [bulk, setBulk] = useState(false);

  const blocks = useSWR<Page<Block>>(`/v1/blocks/${query({ condominium: condo.id, page_size: 200 })}`);
  const units = useSWR<Page<Unit>>(
    `/v1/units/${query({ condominium: condo.id, block: typeof blockFilter === "number" ? blockFilter : undefined, block__isnull: blockFilter === "none" ? true : undefined, search: unitSearch(search), page })}`,
    { keepPreviousData: true },
  );
  const blockOptions = (blocks.data?.results ?? []).map((b) => ({ value: b.id, label: b.name }));
  const blockName = (id: number | null) => blocks.data?.results.find((b) => b.id === id)?.name ?? "—";

  if (!isAdmin) return <Card><Empty>Blocks and units are managed by the site admin.</Empty></Card>;

  const unitFields: FieldDef[] = [
    { name: "block", label: "Block", type: "select", options: blockOptions, hint: "Leave empty for landed houses." },
    { name: "floor", label: "Floor", placeholder: "05", hint: "Two digits, e.g. 05. Empty for landed." },
    { name: "unit_number", label: "Unit number", required: true, placeholder: "12" },
    { name: "is_active", label: "Active", type: "checkbox" },
  ];

  return (
    <>
      <PageHeader
        title="Blocks & units"
        description="The building structure residents, intercom and invitations refer to. Units read like #05-12."
        action={<><Button onClick={() => setBulk(true)}>Generate units</Button><Button variant="primary" onClick={() => setEditingUnit("new")}><Icon name="plus" className="h-4 w-4" /> Add unit</Button></>}
      />
      <div className="grid gap-6 lg:grid-cols-[18rem_1fr]">
        <Card className="self-start">
          <CardHeader title="Blocks" action={<Button size="sm" onClick={() => setEditingBlock("new")}><Icon name="plus" className="h-4 w-4" /> Add</Button>} />
          {!blocks.data ? <Loading /> : (
            <ul className="p-2">
              {[{ key: "", label: "All units" }, ...blocks.data.results.map((b) => ({ key: b.id, label: b.name, block: b })), { key: "none", label: "No block (landed)" }].map((item) => (
                <li key={String(item.key)} className="group flex items-center gap-1">
                  <button
                    onClick={() => { setBlockFilter(item.key as typeof blockFilter); setPage(1); }}
                    className={cx("flex-1 rounded-md px-3 py-2 text-left text-sm", blockFilter === item.key ? "bg-primary-50 font-medium text-primary-600" : "text-body hover:bg-surface-2")}
                  >
                    {item.label}
                  </button>
                  {"block" in item && item.block && (
                    <span className="hidden gap-1 group-hover:flex">
                      <button className="rounded px-1.5 py-1 text-xs text-muted hover:text-primary-600" onClick={() => setEditingBlock(item.block!)}>Rename</button>
                      <button className="rounded px-1.5 py-1 text-xs text-muted hover:text-rose-600" onClick={() => setDeletingBlock(item.block!)}>Delete</button>
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card>
          <div className="border-b border-line p-4">
            <SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Search unit, e.g. 05-12" />
          </div>
          {!units.data ? <Loading /> : units.data.results.length === 0 ? (
            <Empty>No units yet. Use <strong>Generate units</strong> to create a whole block at once.</Empty>
          ) : (
            <Table>
              <thead><tr><Th>Unit</Th><Th>Block</Th><Th>Floor</Th><Th>Status</Th><Th /></tr></thead>
              <tbody className="divide-y divide-line">
                {units.data.results.map((u) => (
                  <tr key={u.id}>
                    <Td className="font-medium text-ink">{u.label}</Td>
                    <Td>{blockName(u.block)}</Td>
                    <Td>{u.floor || "—"}</Td>
                    <Td>{u.is_active ? <Badge tone="green">Active</Badge> : <Badge>Inactive</Badge>}</Td>
                    <Td className="whitespace-nowrap text-right">
                      <Button size="sm" variant="ghost" onClick={() => setEditingUnit(u)}>Edit</Button>
                      <Button size="sm" variant="ghost" onClick={() => setDeletingUnit(u)}>Delete</Button>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
          {units.data && <Pagination page={page} count={units.data.count} onPage={setPage} />}
        </Card>
      </div>

      {editingBlock && (
        <EntityModal
          title={editingBlock === "new" ? "Add block" : `Rename ${editingBlock.name}`}
          fields={blockFields}
          record={editingBlock === "new" ? null : editingBlock}
          endpoint={editingBlock === "new" ? "/v1/blocks/" : `/v1/blocks/${editingBlock.id}/`}
          extra={{ condominium: condo.id }}
          onClose={() => setEditingBlock(null)}
          onSaved={() => { setEditingBlock(null); blocks.mutate(); units.mutate(); }}
        />
      )}
      {editingUnit && (
        <EntityModal
          title={editingUnit === "new" ? "Add unit" : `Edit ${editingUnit.display_name}`}
          fields={unitFields}
          record={editingUnit === "new" ? null : editingUnit}
          defaults={{ is_active: true, block: typeof blockFilter === "number" ? blockFilter : "" }}
          endpoint={editingUnit === "new" ? "/v1/units/" : `/v1/units/${editingUnit.id}/`}
          extra={{ condominium: condo.id }}
          onClose={() => setEditingUnit(null)}
          onSaved={() => { setEditingUnit(null); units.mutate(); }}
        />
      )}
      <ConfirmDialog
        open={!!deletingBlock}
        title="Delete block?"
        message={<>Delete <strong>{deletingBlock?.name}</strong>? A block that still has units cannot be deleted.</>}
        confirmLabel="Delete block"
        onConfirm={async () => { await remove(`/v1/blocks/${deletingBlock!.id}/`); blocks.mutate(); if (blockFilter === deletingBlock!.id) setBlockFilter(""); }}
        onClose={() => setDeletingBlock(null)}
      />
      <ConfirmDialog
        open={!!deletingUnit}
        title="Delete unit?"
        message={<>Delete <strong>{deletingUnit?.display_name}</strong>, its residents&apos; links, vehicles and invitations? To keep history, edit the unit and untick <em>Active</em> instead.</>}
        confirmLabel="Delete unit"
        onConfirm={async () => { await remove(`/v1/units/${deletingUnit!.id}/`); units.mutate(); }}
        onClose={() => setDeletingUnit(null)}
      />
      {bulk && <BulkUnits condoId={condo.id} blocks={blocks.data?.results ?? []} defaultBlock={typeof blockFilter === "number" ? blockFilter : null} onClose={() => setBulk(false)} onDone={() => { setBulk(false); units.mutate(); }} />}
    </>
  );
}

function BulkUnits({ condoId, blocks, defaultBlock, onClose, onDone }: { condoId: number; blocks: Block[]; defaultBlock: number | null; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [block, setBlock] = useState<string>(defaultBlock ? String(defaultBlock) : blocks[0] ? String(blocks[0].id) : "");
  const [from, setFrom] = useState("2");
  const [to, setTo] = useState("10");
  const [numbers, setNumbers] = useState("01-08");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const floors = Math.max(0, Number(to) - Number(from) + 1);
  const perFloor = numbers.split(",").reduce((n, part) => {
    const [a, b] = part.trim().split("-");
    return n + (b !== undefined ? Math.max(0, Number(b) - Number(a) + 1) : a ? 1 : 0);
  }, 0);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await api<{ created: number; skipped: number }>("/v1/units/bulk/", {
        method: "POST",
        body: { condominium: condoId, block: block ? Number(block) : null, floor_from: Number(from), floor_to: Number(to), units: numbers },
      });
      toast("success", `${result.created} units created${result.skipped ? `, ${result.skipped} already existed` : ""}.`);
      onDone();
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} title="Generate units" footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" busy={busy} type="submit" form="bulk-units">Create {floors * perFloor || ""} units</Button></>}>
      <form id="bulk-units" onSubmit={submit} className="space-y-4">
        <ErrorNote error={error} />
        <Field label="Block">
          <Select value={block} onChange={(e) => setBlock(e.target.value)}>
            <option value="">No block</option>
            {blocks.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </Select>
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label="From floor"><Input type="number" min={1} max={99} value={from} onChange={(e) => setFrom(e.target.value)} required /></Field>
          <Field label="To floor"><Input type="number" min={1} max={99} value={to} onChange={(e) => setTo(e.target.value)} required /></Field>
        </div>
        <Field label="Unit numbers on each floor" hint="Ranges and lists, e.g. 01-08 or 01,02,05,07.">
          <Input value={numbers} onChange={(e) => setNumbers(e.target.value)} required />
        </Field>
        <p className="rounded-md bg-primary-50 px-3 py-2 text-sm text-primary-700">
          Creates #{String(from).padStart(2, "0")}-{numbers.split(/[,-]/)[0]?.trim() || "01"} … #{String(to).padStart(2, "0")}-… ({floors} floors × {perFloor} units). Existing units are skipped.
        </p>
      </form>
    </Modal>
  );
}
