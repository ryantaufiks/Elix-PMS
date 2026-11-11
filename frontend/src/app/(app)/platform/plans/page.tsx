"use client";

import { useState } from "react";
import useSWR from "swr";

import { ConfirmDialog } from "@/components/forms";
import { Icon } from "@/components/icons";
import { useModuleCatalogue } from "@/components/ModuleGate";
import { Badge, Button, Card, Checkbox, Empty, ErrorNote, Field, Input, Loading, Modal, PageHeader, Textarea, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { ModuleCatalogue, Plan } from "@/lib/types";

type Draft = Omit<Plan, "id" | "subscriptions" | "updated_at">;
const EMPTY: Draft = { code: "", name: "", description: "", modules: ["core"], limits: {}, overage_rates: {}, currency: "SGD", sort_order: 50, is_public: true, is_active: true };

/** Turning a module on brings what it needs; turning one off takes what needs it. */
function toggleModule(catalogue: ModuleCatalogue, modules: string[], key: string, on: boolean): string[] {
  const set = new Set(modules);
  const visit = (k: string) => {
    if (on) {
      set.add(k);
      catalogue.modules.find((m) => m.key === k)?.requires.forEach(visit);
    } else {
      set.delete(k);
      catalogue.modules.filter((m) => m.requires.includes(k)).forEach((m) => set.has(m.key) && visit(m.key));
    }
  };
  visit(key);
  set.add("core");
  return catalogue.modules.map((m) => m.key).filter((k) => set.has(k));
}

function PlanEditor({ plan, catalogue, onClose, onSaved }: { plan: Plan | null; catalogue: ModuleCatalogue; onClose: () => void; onSaved: () => void }) {
  const [draft, setDraft] = useState<Draft>(plan ? { ...plan } : EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setDraft((d) => ({ ...d, [k]: v }));

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api(plan ? `/v1/plans/${plan.id}/` : "/v1/plans/", { method: plan ? "PATCH" : "POST", body: draft });
      onSaved();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open wide title={plan ? `Edit ${plan.name}` : "Add plan"} onClose={onClose}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" busy={busy} onClick={save}>Save plan</Button></>}>
      <div className="space-y-5">
        <ErrorNote error={error} />
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Name"><Input value={draft.name} onChange={(e) => set("name", e.target.value)} placeholder="Standard" /></Field>
          <Field label="Code" hint="Lowercase, unique."><Input value={draft.code} disabled={!!plan} onChange={(e) => set("code", e.target.value.toLowerCase().replace(/[^a-z0-9-]+/g, "-"))} placeholder="standard" /></Field>
          <Field label="Order" hint="Lower first."><Input type="number" value={draft.sort_order} onChange={(e) => set("sort_order", Number(e.target.value))} /></Field>
        </div>
        <Field label="Description"><Textarea rows={2} value={draft.description} onChange={(e) => set("description", e.target.value)} /></Field>
        <div className="flex flex-wrap gap-6">
          <Checkbox label="Offered to customers (shown in upgrade hints)" checked={draft.is_public} onChange={(e) => set("is_public", e.target.checked)} />
          <Checkbox label="Active (can be given to sites)" checked={draft.is_active} onChange={(e) => set("is_active", e.target.checked)} />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-ink">Modules</h3>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            {catalogue.modules.map((m) => (
              <label key={m.key} className="flex items-start gap-2 rounded-lg border border-line p-3 text-sm">
                <input type="checkbox" className="mt-0.5 h-4 w-4" checked={draft.modules.includes(m.key)}
                  disabled={m.key === "core" || (!m.available && !draft.modules.includes(m.key))}
                  onChange={(e) => set("modules", toggleModule(catalogue, draft.modules, m.key, e.target.checked))} />
                <span>
                  <span className="font-medium text-ink">{m.name}</span>{!m.available && <span className="ml-2"><Badge>Coming soon</Badge></span>}
                  <span className="block text-xs text-muted">{m.description}</span>
                </span>
              </label>
            ))}
          </div>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-ink">Limits</h3>
          <p className="text-xs text-muted">Leave empty for unlimited. Monthly allowances keep working when used up; use above them is overage, priced below. Limits marked “later” are shown to sites now and enforced in a later release.</p>
          <div className="mt-2 grid gap-3 sm:grid-cols-3">
            {catalogue.limits.map((l) => (
              <Field key={l.key} label={`${l.name}${l.unit ? ` (${l.unit})` : ""}${l.enforced || l.metered ? "" : " · later"}`}>
                <Input type="number" min={0} value={draft.limits[l.key] ?? ""} placeholder="Unlimited"
                  onChange={(e) => set("limits", { ...Object.fromEntries(Object.entries(draft.limits).filter(([k]) => k !== l.key)),
                    ...(e.target.value === "" ? {} : { [l.key]: Number(e.target.value) }) })} />
              </Field>
            ))}
          </div>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-ink">Overage prices</h3>
          <p className="text-xs text-muted">Price per unit above the monthly allowance, for the usage report and invoices.</p>
          <div className="mt-2 grid gap-3 sm:grid-cols-3">
            <Field label="Currency"><Input value={draft.currency} maxLength={3} onChange={(e) => set("currency", e.target.value.toUpperCase())} /></Field>
            {catalogue.limits.filter((l) => l.metered).map((l) => (
              <Field key={l.key} label={`${l.name}, per ${l.key === "intercom_minutes" ? "minute" : "conversation"}`}>
                <Input type="number" min={0} step="0.01" value={draft.overage_rates[l.key] ?? ""} placeholder="0"
                  onChange={(e) => set("overage_rates", { ...Object.fromEntries(Object.entries(draft.overage_rates).filter(([k]) => k !== l.key)),
                    ...(e.target.value === "" ? {} : { [l.key]: Number(e.target.value) }) })} />
              </Field>
            ))}
          </div>
        </div>
      </div>
    </Modal>
  );
}

export default function PlansPage() {
  const { me } = useSession();
  const toast = useToast();
  const catalogue = useModuleCatalogue();
  const { data, mutate } = useSWR<Plan[]>(me.is_superuser ? "/v1/plans/" : null);
  const [editing, setEditing] = useState<Plan | "new" | null>(null);
  const [deleting, setDeleting] = useState<Plan | null>(null);

  if (!me.is_superuser) return <Card><Empty>Only the platform administrator manages plans.</Empty></Card>;

  return (
    <>
      <PageHeader title="Plans" description="What each package includes and its limits. Give a site its plan under Condominiums → Subscription."
        action={<Button variant="primary" onClick={() => setEditing("new")}><Icon name="plus" className="h-4 w-4" /> Add plan</Button>} />
      {!data || !catalogue ? <Loading /> : data.length === 0 ? <Card><Empty>No plans.</Empty></Card> : (
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
          {data.map((p) => (
            <Card key={p.id} className={`flex flex-col ${p.is_active ? "" : "opacity-70"}`}>
              <div className="border-b border-line p-5">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-xl font-semibold text-ink">{p.name}</h2>
                  {!p.is_public && <Badge>Internal</Badge>}
                  {!p.is_active && <Badge tone="amber">Not offered</Badge>}
                </div>
                {p.description && <p className="mt-1 text-sm text-muted">{p.description}</p>}
                <p className="mt-3 text-sm text-body"><strong className="text-ink">{p.subscriptions}</strong> site{p.subscriptions === 1 ? "" : "s"} on this plan</p>
              </div>
              <ul className="space-y-2 p-5 text-sm">
                {catalogue.modules.filter((m) => m.available || p.modules.includes(m.key)).map((m) => {
                  const on = p.modules.includes(m.key) || m.key === "core";
                  return (
                    <li key={m.key} className="flex items-center gap-2">
                      <Icon name={!m.available ? "sparkle" : on ? "check" : "x"} className={`h-4 w-4 shrink-0 ${!m.available ? "text-primary-500" : on ? "text-emerald-500" : "text-muted"}`} />
                      <span className={on ? "text-ink" : "text-muted line-through decoration-slate-400/60"}>{m.name}</span>
                      {!m.available && <span className="ml-auto text-xs text-muted">soon</span>}
                    </li>
                  );
                })}
              </ul>
              <dl className="mx-5 mb-5 divide-y divide-line rounded-xl bg-surface-3/60 px-3 text-sm">
                {catalogue.limits.filter((l) => l.enforced || l.metered).map((l) => (
                  <div key={l.key} className="flex items-baseline justify-between gap-3 py-1.5">
                    <dt className="text-muted">{l.name}{l.metered ? " / month" : ""}</dt>
                    <dd className="text-right font-medium text-ink">
                      {p.limits[l.key] ?? "∞"}
                      {l.metered && p.overage_rates[l.key] !== undefined && <span className="block text-xs font-normal text-muted">+{p.currency} {p.overage_rates[l.key]} each over</span>}
                    </dd>
                  </div>
                ))}
              </dl>
              <div className="mt-auto flex gap-2 border-t border-line p-4">
                <Button className="flex-1" onClick={() => setEditing(p)}>Edit plan</Button>
                {p.subscriptions === 0 && <Button variant="ghost" onClick={() => setDeleting(p)}>Delete</Button>}
              </div>
            </Card>
          ))}
          <button onClick={() => setEditing("new")}
            className="flex min-h-48 flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-line text-muted transition hover:border-primary-400/60 hover:text-primary-600">
            <Icon name="plus" className="h-6 w-6" />
            <span className="font-medium">Add plan</span>
          </button>
        </div>
      )}
      {editing && catalogue && (
        <PlanEditor plan={editing === "new" ? null : editing} catalogue={catalogue} onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); mutate(); toast("success", "Plan saved. Sites on it are updated."); }} />
      )}
      <ConfirmDialog open={!!deleting} title="Delete plan" confirmLabel="Delete" onClose={() => setDeleting(null)}
        message={<>Delete <strong>{deleting?.name}</strong>? No site is on it.</>}
        onConfirm={async () => { await api(`/v1/plans/${deleting!.id}/`, { method: "DELETE" }); mutate(); }} />
    </>
  );
}
