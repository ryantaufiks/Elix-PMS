"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";

import { OpenGateDialog } from "@/components/bits";
import { BarList, Sparkline, TrafficChart } from "@/components/charts";
import { Icon, type IconName } from "@/components/icons";
import { Button, Card, CardHeader, cx, Empty, Loading, PageHeader } from "@/components/ui";
import { query } from "@/lib/api";
import { METHOD_LABEL, timeAgo } from "@/lib/format";
import { useLiveEvents } from "@/lib/live";
import { useSession } from "@/lib/session";
import type { AccessLog, Gate, Page, Summary } from "@/lib/types";

const METHOD_ICON: Record<string, IconName> = { lpr: "car", qr: "qr", intercom: "phone", app: "smartphone", manual: "hand" };
const sgHour = () => Number(new Intl.DateTimeFormat("en-SG", { hour: "numeric", hourCycle: "h23", timeZone: "Asia/Singapore" }).format(new Date()));

function Kpi({ label, value, icon, footer, children, href }: {
  label: string; value: React.ReactNode; icon: IconName; footer?: React.ReactNode; children?: React.ReactNode; href?: string;
}) {
  const body = (
    <Card className={cx("flex h-full flex-col p-4 sm:p-5", href && "transition-colors hover:border-primary-300 dark:hover:border-primary-700")}>
      <div className="flex items-start justify-between gap-3">
        <div className="text-xs font-medium text-muted sm:text-sm">{label}</div>
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-500/10 text-primary-600 sm:h-9 sm:w-9 dark:text-primary-300">
          <Icon name={icon} className="h-[18px] w-[18px]" />
        </span>
      </div>
      <div className="mt-1 text-2xl font-semibold tracking-tight text-ink sm:text-3xl">{value}</div>
      {children}
      {footer && <div className="mt-auto pt-3 text-xs text-muted">{footer}</div>}
    </Card>
  );
  return href ? <Link href={href} className="block h-full">{body}</Link> : body;
}

function StatusLine({ ok, okText, badText }: { ok: boolean; okText: string; badText: string }) {
  return (
    <span className={cx("inline-flex items-center gap-1.5 font-medium", ok ? "text-emerald-700 dark:text-emerald-300" : "text-amber-700 dark:text-amber-300")}>
      <Icon name={ok ? "check" : "alert"} className="h-3.5 w-3.5" />
      {ok ? okText : badText}
    </span>
  );
}

function FeedItem({ log }: { log: AccessLog }) {
  const subject = [log.plate_number, log.unit_display, log.visitor_name].filter(Boolean).join(" · ") || log.reason || "Gate event";
  const tone = log.result === "granted" ? "text-emerald-600 bg-emerald-500/10 dark:text-emerald-300" : log.result === "denied" ? "text-rose-600 bg-rose-500/10 dark:text-rose-300" : "text-amber-600 bg-amber-500/10 dark:text-amber-300";
  return (
    <li className="flex items-start gap-3 px-5 py-3">
      <span className={cx("mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full", tone)}>
        <Icon name={METHOD_ICON[log.method] ?? "list"} className="h-4 w-4" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium text-ink">{subject}</div>
        <div className="truncate text-xs text-muted">
          {log.result === "granted" ? "Granted" : log.result === "denied" ? "Denied" : "Error"} · {METHOD_LABEL[log.method]} · {log.gate_name || "—"}
          {log.actor_name && ` · ${log.actor_name}`}
        </div>
      </div>
      <time className="shrink-0 text-xs tabular-nums text-muted" dateTime={log.occurred_at}>{timeAgo(log.occurred_at)}</time>
    </li>
  );
}

export default function DashboardPage() {
  const { condo, isAdmin, me } = useSession();
  const [opening, setOpening] = useState<Gate | null>(null);
  const summary = useSWR<Summary>(`/v1/dashboard/summary/${query({ condominium: condo.id })}`, { refreshInterval: 60_000 });
  const logs = useSWR<Page<AccessLog>>(`/v1/access-logs/${query({ condominium: condo.id, page_size: 7 })}`);
  const gates = useSWR<Page<Gate>>(`/v1/gates/${query({ condominium: condo.id, page_size: 200 })}`);

  useLiveEvents((event) => {
    if (event.data.condominium !== condo.id) return;
    summary.mutate();
    if (event.type === "access_log") {
      logs.mutate((p) => p && { ...p, results: [event.data, ...p.results.filter((l) => l.id !== event.data.id)].slice(0, 7) }, { revalidate: false });
    }
  });

  const s = summary.data;
  const nowHour = sgHour();
  const decided = s ? s.granted_today + s.denied_today + s.errors_today : 0;
  const devicesTotal = s ? s.relays_total + s.cameras_total + s.kiosks_total : 0;
  const deviceIssues = s ? s.relays_failing + s.cameras_offline + s.kiosks_offline : 0;
  const greeting = nowHour < 12 ? "Good morning" : nowHour < 18 ? "Good afternoon" : "Good evening";
  const gateHealth = new Map((s?.gates ?? []).map((g) => [g.id, g]));
  const activeGates = (gates.data?.results ?? []).filter((g) => g.is_active);

  return (
    <>
      <PageHeader
        title={`${greeting}, ${me.first_name || me.username}`}
        description={`${condo.name} · ${new Intl.DateTimeFormat("en-SG", { weekday: "long", day: "numeric", month: "long", timeZone: "Asia/Singapore" }).format(new Date())}`}
        action={<Link href="/access/"><Button><Icon name="list" className="h-4 w-4" /> Access log</Button></Link>}
      />

      {s && s.lpr_enabled === false && (
        <div className="mb-5 flex items-start gap-3 rounded-xl border border-amber-500/25 bg-amber-500/10 px-4 py-3 text-sm text-amber-800 dark:text-amber-200">
          <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
          <span>Licence-plate recognition is <strong>off</strong> for this site: camera reads are recorded but never open a gate.{isAdmin && <> Turn it on in <Link href="/setup/site/" className="font-medium underline">Site settings</Link>.</>}</span>
        </div>
      )}

      {/* Four compact tiles on a phone (2x2), so the chart and feed are one swipe away. */}
      <div className="grid grid-cols-2 gap-3 sm:gap-5 xl:grid-cols-4">
        <Kpi label="Entries granted today" value={s?.granted_today ?? "–"} icon="arrowUp" href="/access/"
          footer={s && decided ? `${Math.round((s.granted_today / decided) * 100)}% of ${decided} gate decisions` : "No gate decisions yet today"}>
          {s && <Sparkline values={s.hourly.slice(0, nowHour + 1).map((h) => h.granted)} className="mt-2" />}
        </Kpi>
        <Kpi label="Denied today" value={s?.denied_today ?? "–"} icon="shield" href="/access/"
          footer={s && <StatusLine ok={!s.errors_today} okText="No relay errors" badText={`${s.errors_today} relay error${s.errors_today === 1 ? "" : "s"}`} />} />
        <Kpi label="Visitors expected" value={s?.invitations_today ?? "–"} icon="ticket" href="/invitations/"
          footer={s && (s.open_calls ? <StatusLine ok={false} okText="" badText={`${s.open_calls} intercom call${s.open_calls === 1 ? "" : "s"} ringing`} /> : "Active invitations valid today")} />
        <Kpi label="Devices online" value={s ? `${devicesTotal - deviceIssues}/${devicesTotal}` : "–"} icon="cpu" href={isAdmin ? "/setup/devices/" : undefined}
          footer={s && (devicesTotal ? <StatusLine ok={!deviceIssues} okText="All devices healthy" badText={`${deviceIssues} need${deviceIssues === 1 ? "s" : ""} attention`} /> : "No devices configured")} />
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Traffic today" action={<span className="text-xs text-muted">Gate decisions per hour (SGT)</span>} />
          <div className="p-5">{s ? <TrafficChart data={s.hourly} nowHour={nowHour} /> : <Loading />}</div>
        </Card>
        <Card className="flex flex-col">
          <CardHeader title="Live activity" action={<Link href="/access/" className="text-sm font-medium text-primary-600 hover:underline dark:text-primary-300">View all</Link>} />
          {!logs.data ? <Loading /> : logs.data.results.length === 0 ? <Empty>No activity yet. Events appear here the moment they happen.</Empty> : (
            <ul className="divide-y divide-line">{logs.data.results.map((log) => <FeedItem key={log.id} log={log} />)}</ul>
          )}
        </Card>
      </div>

      <div className="mt-5 grid items-start gap-5 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Gates" action={isAdmin && <Link href="/setup/devices/" className="text-sm font-medium text-primary-600 hover:underline dark:text-primary-300">Manage</Link>} />
          {!gates.data ? <Loading /> : activeGates.length === 0 ? (
            <Empty>No active gates yet.{isAdmin && <> Add them under <Link className="font-medium text-primary-600 dark:text-primary-300 hover:underline" href="/setup/devices/">Gates &amp; devices</Link>.</>}</Empty>
          ) : (
            <ul className="grid gap-px bg-line sm:grid-cols-2">
              {activeGates.map((gate) => {
                const health = gateHealth.get(gate.id);
                const status = !health || health.relays_total === 0
                  ? { text: "No relay", cls: "text-muted", icon: "alert" as IconName }
                  : health.relays_failing
                    ? { text: "Relay error", cls: "text-rose-600 dark:text-rose-300", icon: "alert" as IconName }
                    : { text: "Relay OK", cls: "text-emerald-700 dark:text-emerald-300", icon: "check" as IconName };
                return (
                  <li key={gate.id} className="flex items-center justify-between gap-3 bg-surface px-5 py-4">
                    <div className="flex min-w-0 items-center gap-3">
                      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-surface-3 text-body">
                        <Icon name={gate.gate_type === "vehicle" ? "car" : gate.gate_type === "door" ? "key" : "gate"} className="h-5 w-5" />
                      </span>
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium text-ink">{gate.name}</div>
                        <div className={cx("flex items-center gap-1 text-xs", status.cls)}><Icon name={status.icon} className="h-3.5 w-3.5" />{status.text}</div>
                      </div>
                    </div>
                    <Button size="sm" variant="primary" onClick={() => setOpening(gate)} disabled={!health || health.relays_total === 0}
                      title={!health || health.relays_total === 0 ? "No relay is wired to this gate yet (Gates & devices → Relays)" : undefined}>
                      <Icon name="unlock" className="h-4 w-4" /> Open
                    </Button>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
        <Card>
          <CardHeader title="Entry methods today" />
          <div className="p-5">
            {s ? (
              decided ? <BarList rows={(["lpr", "qr", "intercom", "app", "manual"] as const).map((m) => ({ label: METHOD_LABEL[m], value: s.by_method[m] ?? 0 }))} />
                : <p className="py-6 text-center text-sm text-muted">Nothing yet today.</p>
            ) : <Loading />}
          </div>
        </Card>
      </div>
      <OpenGateDialog gate={opening} onClose={() => setOpening(null)} />
    </>
  );
}
