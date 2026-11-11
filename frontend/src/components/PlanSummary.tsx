"use client";

import useSWR from "swr";

import { Icon } from "./icons";
import { useModuleCatalogue } from "./ModuleGate";
import { Badge, Card, CardHeader, Loading } from "./ui";
import { formatDate } from "@/lib/format";
import type { Subscription, SubscriptionStatus } from "@/lib/types";

export const STATUS: Record<SubscriptionStatus, { label: string; tone: "green" | "blue" | "amber" | "red" | "slate" }> = {
  trial: { label: "Trial", tone: "blue" },
  active: { label: "Active", tone: "green" },
  grace: { label: "Grace period", tone: "amber" },
  suspended: { label: "Suspended", tone: "red" },
  cancelled: { label: "Cancelled", tone: "slate" },
};

/** "until 30 Nov 2026" for the subscription's current status. */
export function statusDate(sub: Pick<Subscription, "status" | "trial_ends_on" | "period_ends_on">) {
  const date = sub.status === "trial" ? sub.trial_ends_on : sub.period_ends_on;
  return date ? `until ${formatDate(date)}` : "";
}

export function UsageBar({ used, allowed }: { used: number; allowed: number | null | undefined }) {
  if (allowed === null || allowed === undefined) return <span className="text-xs text-muted">{used} · unlimited</span>;
  const pct = allowed === 0 ? 100 : Math.min(100, Math.round((used / allowed) * 100));
  const tone = pct >= 100 ? "bg-rose-500" : pct >= 80 ? "bg-amber-500" : "bg-primary-500";
  return (
    <div className="min-w-32">
      <div className="text-xs text-muted">{used} of {allowed}</div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-3"><div className={`h-full ${tone}`} style={{ width: `${pct}%` }} /></div>
    </div>
  );
}

/** The site's plan for its site admin: status, modules and limits with usage. Read-only. */
export function PlanSummary({ condoId }: { condoId: number }) {
  const { data } = useSWR<Subscription>(`/v1/subscriptions/${condoId}/`);
  const catalogue = useModuleCatalogue();
  if (!data || !catalogue) return <Card className="max-w-4xl"><CardHeader title="Your plan" /><Loading /></Card>;
  const status = STATUS[data.status];
  return (
    <Card className="max-w-4xl">
      <CardHeader title={`Your plan: ${data.plan_name}`} action={<Badge tone={status.tone}>{status.label} {statusDate(data)}</Badge>} />
      <div className="grid gap-6 p-5 sm:grid-cols-2 sm:p-6">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-muted">Modules</h3>
          <ul className="mt-3 space-y-2">
            {catalogue.modules.map((m) => {
              const on = m.available && data.modules.includes(m.key);
              return (
                <li key={m.key} className="flex items-center gap-2 text-sm">
                  <Icon name={on ? "check" : m.available ? "lock" : "sparkle"} className={`h-4 w-4 shrink-0 ${on ? "text-emerald-500" : m.available ? "text-muted" : "text-primary-500"}`} />
                  <span className={on ? "text-ink" : "text-muted"}>{m.name}</span>
                  {!on && <span className="ml-auto text-xs text-muted">{!m.available ? "coming soon" : m.upsell_plan ? `in ${m.upsell_plan}` : "add-on"}</span>}
                </li>
              );
            })}
          </ul>
        </div>
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-muted">Limits</h3>
          <ul className="mt-3 space-y-3">
            {catalogue.limits.filter((l) => l.enforced || l.metered).map((l) => (
              <li key={l.key} className="flex items-center justify-between gap-4 text-sm">
                <span className="text-ink">{l.name}{l.metered && <span className="block text-xs text-muted">this month</span>}</span>
                <UsageBar used={data.usage[l.key] ?? 0} allowed={data.limits[l.key]} />
              </li>
            ))}
          </ul>
          <p className="mt-5 text-xs text-muted">To change your plan or add modules, contact Elix.</p>
        </div>
      </div>
    </Card>
  );
}
