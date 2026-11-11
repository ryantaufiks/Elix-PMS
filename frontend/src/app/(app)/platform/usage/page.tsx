"use client";

import { useState } from "react";
import useSWR from "swr";

import { Icon } from "@/components/icons";
import { STATUS } from "@/components/PlanSummary";
import { Badge, Button, Card, Empty, Field, Input, Loading, PageHeader, Table, Td, Th, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { SubscriptionStatus, UsageRow } from "@/lib/types";

const money = (n: number, currency: string) => `${currency} ${n.toFixed(2)}`;

function Used({ used, allowed, over, amount, currency }: { used: number; allowed: number | null; over: number; amount: number; currency: string }) {
  return (
    <div>
      <div className="text-ink">{used.toLocaleString()} <span className="text-xs text-muted">/ {allowed ?? "∞"}</span></div>
      {over > 0 && <div className="text-xs text-rose-600">+{over.toLocaleString()} over · {money(amount, currency)}</div>}
    </div>
  );
}

export default function UsagePage() {
  const { me } = useSession();
  const toast = useToast();
  const [month, setMonth] = useState(() => new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Singapore" }).slice(0, 7));
  const { data } = useSWR<{ month: string; rows: UsageRow[] }>(me.is_superuser ? `/v1/usage/?month=${month}` : null, { keepPreviousData: true });
  const [busy, setBusy] = useState(false);

  if (!me.is_superuser) return <Card><Empty>Only the platform administrator sees usage across sites.</Empty></Card>;

  const totals = (data?.rows ?? []).reduce<Record<string, number>>((t, r) => ({ ...t, [r.currency]: (t[r.currency] ?? 0) + r.overage_amount }), {});

  async function exportCsv() {
    setBusy(true);
    try {
      const response = await api<Response>(`/v1/usage/?month=${month}&export=csv`, { raw: true });
      const url = URL.createObjectURL(await response.blob());
      Object.assign(document.createElement("a"), { href: url, download: `elix-usage-${month}.csv` }).click();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch {
      toast("error", "Could not export the usage report.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Usage" description="Video intercom minutes and AI conversations per site, against each plan's monthly allowance. Use above it is overage for the invoice."
        action={<Button onClick={exportCsv} busy={busy} disabled={!data?.rows.length}><Icon name="download" className="h-4 w-4" /> Export CSV</Button>} />
      <div className="mb-4 flex flex-wrap items-end gap-4">
        <Field label="Month"><Input type="month" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} className="w-48" /></Field>
        {Object.entries(totals).map(([currency, total]) => (
          <div key={currency} className="pb-2 text-sm text-body">Overage this month: <strong className="text-ink">{money(total, currency)}</strong></div>
        ))}
      </div>
      <Card>
        {!data ? <Loading /> : data.rows.length === 0 ? <Empty>No sites.</Empty> : (
          <Table>
            <thead><tr><Th>Site</Th><Th>Plan</Th><Th>Video intercom (min)</Th><Th>AI conversations</Th><Th>AI tokens</Th><Th>Overage</Th></tr></thead>
            <tbody className="divide-y divide-line">
              {data.rows.map((r) => (
                <tr key={r.site_id}>
                  <Td className="font-medium text-ink">{r.site}<div className="font-mono text-xs font-normal text-muted">{r.code}</div></Td>
                  <Td>{r.plan || "—"}{r.status && <div className="mt-1"><Badge tone={STATUS[r.status as SubscriptionStatus]?.tone ?? "slate"}>{STATUS[r.status as SubscriptionStatus]?.label ?? r.status}</Badge></div>}</Td>
                  <Td><Used used={r.intercom_minutes} allowed={r.intercom_minutes_allowed} over={r.intercom_minutes_overage} amount={r.intercom_minutes_amount} currency={r.currency} /></Td>
                  <Td>
                    <Used used={r.ai_conversations} allowed={r.ai_conversations_allowed} over={r.ai_conversations_overage} amount={r.ai_conversations_amount} currency={r.currency} />
                    {r.ai_conversations_own_key > 0 && <div className="text-xs text-muted">+{r.ai_conversations_own_key} with the site&apos;s own key</div>}
                  </Td>
                  <Td className="text-xs">
                    {r.ai_tokens_in.toLocaleString()} in · {r.ai_tokens_out.toLocaleString()} out
                    {r.ai_cost_usd !== null && <div className="text-muted">≈ USD {r.ai_cost_usd.toFixed(2)}</div>}
                  </Td>
                  <Td className="whitespace-nowrap font-medium text-ink">{r.overage_amount > 0 ? money(r.overage_amount, r.currency) : "—"}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
      <p className="mt-3 text-xs text-muted">Intercom minutes count answered time. AI tokens cover speech-to-text mode; realtime conversations are counted but their tokens are billed by OpenAI directly. Set the AI cost estimate under System settings.</p>
    </>
  );
}
