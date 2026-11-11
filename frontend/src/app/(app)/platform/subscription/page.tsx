"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import useSWR from "swr";

import { useModuleCatalogue } from "@/components/ModuleGate";
import { STATUS, UsageBar } from "@/components/PlanSummary";
import { Badge, Button, Card, CardHeader, Empty, ErrorNote, Field, Input, Loading, PageHeader, Select, Table, Td, Textarea, Th, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Plan, Subscription, SubscriptionStatus } from "@/lib/types";

type Draft = Pick<Subscription, "plan" | "addons" | "disabled_modules" | "limit_overrides" | "status" | "trial_ends_on"
  | "period_ends_on" | "grace_ends_on" | "billing_name" | "billing_email" | "notes">;

const STATUS_HINT: Record<SubscriptionStatus, string> = {
  trial: "Every module of the plan until the trial ends; then grace (or active if paid). Reminders 7 and 1 days before.",
  active: "Paid: everything in the plan and add-ons. Grace starts the day after Paid until.",
  grace: "Payment overdue: everything still works for 14 days; the site admin sees a banner and gets an email.",
  suspended: "Premium modules off and setup locked; gates, plate access and the basic kiosk keep working, reports still export.",
  cancelled: "Contract ended: the site is closed to its staff. Gates keep working until the data is exported and removed.",
};

export default function SubscriptionPage() {
  const { me, reload } = useSession();
  const toast = useToast();
  const [site, setSite] = useState<number | null>(null);
  useEffect(() => setSite(Number(new URLSearchParams(window.location.search).get("site")) || null), []);
  const catalogue = useModuleCatalogue();
  const { data: plans } = useSWR<Plan[]>(me.is_superuser ? "/v1/plans/" : null);
  const { data, mutate } = useSWR<Subscription>(me.is_superuser && site ? `/v1/subscriptions/${site}/` : null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    if (data) setDraft({ plan: data.plan, addons: data.addons, disabled_modules: data.disabled_modules, limit_overrides: data.limit_overrides,
      status: data.status, trial_ends_on: data.trial_ends_on, period_ends_on: data.period_ends_on, grace_ends_on: data.grace_ends_on, billing_name: data.billing_name,
      billing_email: data.billing_email, notes: data.notes ?? "" });
  }, [data]);

  if (!me.is_superuser) return <Card><Empty>Only the platform administrator manages subscriptions.</Empty></Card>;
  if (!data || !draft || !catalogue || !plans) return <Loading />;

  const plan = plans.find((p) => p.id === draft.plan);
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setDraft((d) => (d ? { ...d, [k]: v } : d));
  const toggle = (field: "addons" | "disabled_modules", key: string, on: boolean) =>
    set(field, on ? [...draft[field], key] : draft[field].filter((k) => k !== key));

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api(`/v1/subscriptions/${site}/`, { method: "PATCH", body: draft });
      await mutate();
      await reload();
      toast("success", "Subscription saved. The site's modules apply at once.");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title={`${data.condominium_name} · Subscription`} description="Plan, add-ons, modules switched off, limits and billing for this site."
        action={<Link href="/platform/condominiums/"><Button>Back to condominiums</Button></Link>} />
      <div className="max-w-5xl space-y-6">
        <ErrorNote error={error} />
        <Card>
          <CardHeader title="Plan & status" action={<Badge tone={STATUS[data.status].tone}>{STATUS[data.status].label}</Badge>} />
          <div className="grid gap-4 p-5 sm:grid-cols-2 sm:p-6">
            <Field label="Plan">
              <Select value={draft.plan} onChange={(e) => set("plan", Number(e.target.value))}>
                {plans.filter((p) => p.is_active || p.id === data.plan).map((p) => <option key={p.id} value={p.id}>{p.name}{p.is_public ? "" : " (internal)"}</option>)}
              </Select>
            </Field>
            <Field label="Status" hint={STATUS_HINT[draft.status]}>
              <Select value={draft.status} onChange={(e) => set("status", e.target.value as SubscriptionStatus)}>
                {Object.entries(STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </Select>
            </Field>
            <Field label="Trial ends"><Input type="date" value={draft.trial_ends_on ?? ""} onChange={(e) => set("trial_ends_on", e.target.value || null)} /></Field>
            <Field label="Paid until" hint="After this date the site moves to its grace period automatically."><Input type="date" value={draft.period_ends_on ?? ""} onChange={(e) => set("period_ends_on", e.target.value || null)} /></Field>
            {draft.status === "grace" && (
              <Field label="Grace ends" hint="Suspended the day after. Empty: 14 days from today.">
                <Input type="date" value={draft.grace_ends_on ?? ""} onChange={(e) => set("grace_ends_on", e.target.value || null)} />
              </Field>
            )}
          </div>
        </Card>

        <Card>
          <CardHeader title="Modules" />
          <Table>
            <thead><tr><Th>Module</Th><Th>In plan</Th><Th>Add-on</Th><Th>Switch off</Th><Th>Now</Th></tr></thead>
            <tbody className="divide-y divide-line">
              {catalogue.modules.map((m) => {
                const inPlan = m.key === "core" || !!plan?.modules.includes(m.key);
                const on = data.modules.includes(m.key);
                return (
                  <tr key={m.key}>
                    <Td><span className="font-medium text-ink">{m.name}</span>{!m.available && <span className="ml-2"><Badge>Coming soon</Badge></span>}
                      {m.requires.length > 0 && <div className="text-xs text-muted">Needs {m.requires.map((r) => catalogue.modules.find((x) => x.key === r)?.name).join(", ")}</div>}</Td>
                    <Td>{inPlan ? "✓" : ""}</Td>
                    <Td><input type="checkbox" aria-label={`Add ${m.name}`} className="h-4 w-4" disabled={inPlan || (!m.available && !draft.addons.includes(m.key))}
                      checked={draft.addons.includes(m.key)} onChange={(e) => toggle("addons", m.key, e.target.checked)} /></Td>
                    <Td><input type="checkbox" aria-label={`Switch off ${m.name}`} className="h-4 w-4" disabled={m.key === "core"}
                      checked={draft.disabled_modules.includes(m.key)} onChange={(e) => toggle("disabled_modules", m.key, e.target.checked)} /></Td>
                    <Td>{!m.available ? <Badge tone="blue">Soon</Badge> : on ? <Badge tone="green">On</Badge> : <Badge>Off</Badge>}</Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
          <p className="px-5 pb-4 pt-2 text-xs text-muted sm:px-6">“Now” shows the saved state. Switching a module off also turns off what needs it; while suspended only physical access stays on.</p>
        </Card>

        <Card>
          <CardHeader title="Limits" />
          <Table>
            <thead><tr><Th>Limit</Th><Th>Plan</Th><Th>This site</Th><Th>In use</Th></tr></thead>
            <tbody className="divide-y divide-line">
              {catalogue.limits.map((l) => (
                <tr key={l.key}>
                  <Td>{l.name}{l.unit && <span className="text-xs text-muted"> ({l.unit})</span>}{l.metered ? <div className="text-xs text-muted">Monthly allowance; use above it is overage</div>
                    : !l.enforced && <div className="text-xs text-muted">Enforced in a later release</div>}</Td>
                  <Td>{plan?.limits[l.key] ?? "Unlimited"}</Td>
                  <Td><Input type="number" min={0} className="w-32" placeholder="As plan" value={draft.limit_overrides[l.key] ?? ""}
                    onChange={(e) => set("limit_overrides", { ...Object.fromEntries(Object.entries(draft.limit_overrides).filter(([k]) => k !== l.key)),
                      ...(e.target.value === "" ? {} : { [l.key]: Number(e.target.value) }) })} /></Td>
                  <Td>{l.key in data.usage ? <UsageBar used={data.usage[l.key]} allowed={data.limits[l.key]} /> : <span className="text-xs text-muted">—</span>}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>

        <Card>
          <CardHeader title="Billing" />
          <div className="grid gap-4 p-5 sm:grid-cols-2 sm:p-6">
            <Field label="Billing contact"><Input value={draft.billing_name} onChange={(e) => set("billing_name", e.target.value)} /></Field>
            <Field label="Billing email" hint="Receives renewal reminders."><Input type="email" value={draft.billing_email} onChange={(e) => set("billing_email", e.target.value)} /></Field>
            <div className="sm:col-span-2"><Field label="Internal notes" hint="Contract, invoice numbers, special terms. Not shown to the site.">
              <Textarea rows={3} value={draft.notes ?? ""} onChange={(e) => set("notes", e.target.value)} /></Field></div>
          </div>
        </Card>

        <div className="flex justify-end"><Button variant="primary" busy={busy} onClick={save}>Save subscription</Button></div>

        <Card>
          <CardHeader title="History" />
          {!data.events?.length ? <Empty>No changes yet.</Empty> : (
            <ul className="divide-y divide-line">
              {data.events.map((e) => (
                <li key={e.id} className="px-5 py-3 text-sm sm:px-6">
                  <div className="text-ink">{e.summary}</div>
                  <div className="text-xs text-muted">{formatDateTime(e.at)} · {e.actor_name}</div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}
