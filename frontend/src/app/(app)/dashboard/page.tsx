"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import useSWR from "swr";

import { OpenGateDialog } from "@/components/bits";
import { BarList, DailyChart, TrafficChart } from "@/components/charts";
import { ConfirmDialog } from "@/components/forms";
import { Icon, type IconName } from "@/components/icons";
import { Badge, Button, Card, CardHeader, cx, Empty, IconButton, Loading, PageHeader, useToast } from "@/components/ui";
import { api, query } from "@/lib/api";
import { formatDateTime, formatTime, METHOD_LABEL, timeAgo, visitPurpose } from "@/lib/format";
import { useLiveEvents } from "@/lib/live";
import { useSession } from "@/lib/session";
import type { AccessLog, Gate, Page, Summary, Visit } from "@/lib/types";

const METHOD_ICON: Record<string, IconName> = { lpr: "car", qr: "qr", intercom: "phone", app: "smartphone", manual: "hand" };
const sgHour = () => Number(new Intl.DateTimeFormat("en-SG", { hour: "numeric", hourCycle: "h23", timeZone: "Asia/Singapore" }).format(new Date()));

const PURPOSE_GROUP: Record<string, string> = {
  guest: "guests", other: "guests", delivery: "deliveries", food: "deliveries", pickup: "deliveries", contractor: "contractors",
};

function Kpi({ label, value, icon, footer, children, href, alert }: {
  label: string; value: React.ReactNode; icon: IconName; footer?: React.ReactNode; children?: React.ReactNode; href?: string; alert?: boolean;
}) {
  const body = (
    <Card className={cx("flex h-full flex-col p-4 sm:p-5", href && "transition-colors hover:border-primary-300 dark:hover:border-primary-700",
      alert && "border-rose-500/40 bg-rose-500/5")}>
      <div className="flex items-start justify-between gap-3">
        <div className="text-xs font-medium text-muted sm:text-sm">{label}</div>
        <span className={cx("flex h-8 w-8 shrink-0 items-center justify-center rounded-lg sm:h-9 sm:w-9",
          alert ? "bg-rose-500/15 text-rose-600 dark:text-rose-300" : "bg-primary-500/10 text-primary-600 dark:text-primary-300")}>
          <Icon name={icon} className="h-[18px] w-[18px]" />
        </span>
      </div>
      <div className={cx("mt-1 text-2xl font-semibold tracking-tight sm:text-3xl", alert ? "text-rose-600 dark:text-rose-300" : "text-ink")}>{value}</div>
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

/** "1:24" or "26 min": how long a visitor has been inside, ticking every 30 seconds. */
function useNow(every = 30_000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), every);
    return () => clearInterval(id);
  }, [every]);
  return now;
}

const sgDay = (iso: string) => new Intl.DateTimeFormat("en-SG", { dateStyle: "short", timeZone: "Asia/Singapore" }).format(new Date(iso));

function stayed(since: string, now: number) {
  const minutes = Math.max(0, Math.floor((now - new Date(since).getTime()) / 60_000));
  return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")} min`;
}

function limitsText(limits: Summary["visitors"]["limits"]) {
  const hours = (m: number) => (m % 60 ? `${m} min` : `${m / 60} h`);
  return [
    limits.delivery_minutes ? `deliveries ${hours(limits.delivery_minutes)}` : "",
    limits.guest_minutes ? `guests ${hours(limits.guest_minutes)}` : "",
    limits.contractor_until ? `contractors ${limits.contractor_until.slice(0, 5)}` : "",
  ].filter(Boolean).join(" · ") || "No limits set";
}

/** Who is inside right now: overstaying first, then the longest stays. */
function OnSite({ visits, onCheckOut }: { visits: Visit[]; onCheckOut: (v: Visit) => void }) {
  const now = useNow();
  const rows = [...visits].sort((a, b) => Number(b.overstaying) - Number(a.overstaying) || a.created_at.localeCompare(b.created_at));
  if (rows.length === 0) return <Empty icon="users" title="Nobody on site">Visitors appear here from the moment they check in until they leave.</Empty>;
  return (
    <ul className="divide-y divide-line">
      {rows.map((v) => (
        <li key={v.id} className={cx("flex items-center gap-3 px-5 py-3", v.overstaying && "bg-rose-500/5")}>
          <span className="w-14 shrink-0 font-mono text-sm font-semibold text-ink">{v.pass_number}</span>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium text-ink">
              {v.visitor_name} <span className="font-normal text-muted">→ {v.unit_display}</span>
            </div>
            <div className="truncate text-xs text-muted">{visitPurpose(v.purpose, v.company)} · in {sgDay(v.created_at) === sgDay(new Date(now).toISOString()) ? formatTime(v.created_at) : formatDateTime(v.created_at)}</div>
          </div>
          <div className="shrink-0 text-right">
            <div className={cx("text-sm tabular-nums", v.overstaying ? "font-semibold text-rose-600 dark:text-rose-300" : "text-body")}>{stayed(v.created_at, now)}</div>
            {v.overstaying ? <Badge tone="red">Overstay</Badge>
              : v.overstay_at && <div className="text-xs text-muted">until {formatTime(v.overstay_at)}</div>}
          </div>
          <IconButton label={`Check out ${v.visitor_name}`} tone="primary" onClick={() => onCheckOut(v)}>
            <Icon name="checkout" className="h-[18px] w-[18px]" />
          </IconButton>
        </li>
      ))}
    </ul>
  );
}

export default function DashboardPage() {
  const { condo, isAdmin, me } = useSession();
  const [opening, setOpening] = useState<Gate | null>(null);
  const summary = useSWR<Summary>(`/v1/dashboard/summary/${query({ condominium: condo.id })}`, { refreshInterval: 60_000 });
  const logs = useSWR<Page<AccessLog>>(`/v1/access-logs/${query({ condominium: condo.id, page_size: 7 })}`);
  const gates = useSWR<Page<Gate>>(`/v1/gates/${query({ condominium: condo.id, page_size: 200 })}`);
  const inside = useSWR<Page<Visit>>(`/v1/visits/${query({ condominium: condo.id, state: "on_site", page_size: 100 })}`, { refreshInterval: 60_000 });
  const [leaving, setLeaving] = useState<Visit | null>(null);
  const toast = useToast();

  useLiveEvents((event) => {
    if (event.data.condominium !== condo.id) return;
    summary.mutate();
    if (event.type === "visit" || event.type === "visit_overstay") inside.mutate();
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
  const v = s?.visitors;
  const groups = v ? Object.entries(v.on_site_by_purpose).reduce<Record<string, number>>((all, [purpose, n]) => {
    const group = PURPOSE_GROUP[purpose] ?? "guests";
    return { ...all, [group]: (all[group] ?? 0) + n };
  }, {}) : {};
  const onSiteBreakdown = Object.entries(groups).map(([group, n]) => `${n} ${n === 1 ? group.replace(/ies$/, "y").replace(/s$/, "") : group}`).join(" · ");
  const diff = v ? v.arrived_today - v.arrived_yesterday_by_now : 0;
  const compareYesterday = v && (v.arrived_yesterday_by_now === 0 && v.arrived_today === 0 ? "Same as yesterday so far"
    : <span className={diff > 0 ? "text-primary-600 dark:text-primary-300" : undefined}>
        {diff === 0 ? "Same as" : `${diff > 0 ? "▲" : "▼"} ${Math.abs(diff)} ${diff > 0 ? "more than" : "fewer than"}`} yesterday at this time ({v.arrived_yesterday_by_now})
      </span>);

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

      {/* Visitors first: what the guardhouse needs. Four compact tiles on a phone (2x2). */}
      <div className="grid grid-cols-2 gap-3 sm:gap-5 xl:grid-cols-4">
        <Kpi label="On site now" value={v?.on_site ?? "–"} icon="users" href="/visits/"
          footer={v && (v.on_site ? onSiteBreakdown : "Nobody inside")} />
        <Kpi label="Arrived today" value={v?.arrived_today ?? "–"} icon="arrowUp" href="/visits/"
          footer={v && compareYesterday} />
        <Kpi label="Left today" value={v?.left_today ?? "–"} icon="checkout" href="/visits/"
          footer="Checked out since midnight" />
        <Kpi label="Overstaying" value={v?.overstaying ?? "–"} icon="alert" alert={!!v?.overstaying} href="#on-site"
          footer={v && `Limits: ${limitsText(v.limits)}`} />
      </div>

      <div className="mt-5 grid items-start gap-5 xl:grid-cols-3">
        <Card className="min-w-0 xl:col-span-2">
          <div id="on-site" className="scroll-mt-24" />
          <CardHeader title={`Visitors on site${inside.data ? ` (${inside.data.count})` : ""}`}
            action={<Link href="/visits/" className="text-sm font-medium text-primary-600 hover:underline dark:text-primary-300">Visitor list</Link>} />
          {!inside.data ? <Loading /> : <OnSite visits={inside.data.results} onCheckOut={setLeaving} />}
        </Card>
        <Card className="flex min-w-0 flex-col">
          <CardHeader title="Live activity" action={<Link href="/access/" className="text-sm font-medium text-primary-600 hover:underline dark:text-primary-300">View all</Link>} />
          {!logs.data ? <Loading /> : logs.data.results.length === 0 ? <Empty>No activity yet. Events appear here the moment they happen.</Empty> : (
            <ul className="divide-y divide-line">{logs.data.results.map((log) => <FeedItem key={log.id} log={log} />)}</ul>
          )}
        </Card>
      </div>

      <div className="mt-5 grid items-start gap-5 xl:grid-cols-3">
        <Card className="min-w-0 xl:col-span-2">
          <CardHeader title="Visitors in and out today" action={<span className="text-xs text-muted">Per hour (SGT)</span>} />
          <div className="p-5">
            {v ? (
              <DailyChart grouped height={240}
                points={v.hourly.slice(0, nowHour + 1).map((h) => ({ date: String(h.hour), arrived: h.arrived, left: h.left }))}
                series={[{ key: "arrived", label: "Arrived" }, { key: "left", label: "Left" }]}
                label={(hour) => `${hour.padStart(2, "0")}:00`} />
            ) : <Loading />}
          </div>
        </Card>
        <Card>
          <CardHeader title="Gates" action={isAdmin && <Link href="/setup/devices/" className="text-sm font-medium text-primary-600 hover:underline dark:text-primary-300">Manage</Link>} />
          {!gates.data ? <Loading /> : activeGates.length === 0 ? (
            <Empty>No active gates yet.{isAdmin && <> Add them under <Link className="font-medium text-primary-600 dark:text-primary-300 hover:underline" href="/setup/devices/">Gates &amp; devices</Link>.</>}</Empty>
          ) : (
            <ul className="divide-y divide-line">
              {activeGates.map((gate) => {
                const health = gateHealth.get(gate.id);
                const status = !health || health.relays_total === 0
                  ? { text: "No relay", cls: "text-muted", icon: "alert" as IconName }
                  : health.relays_failing
                    ? { text: "Relay error", cls: "text-rose-600 dark:text-rose-300", icon: "alert" as IconName }
                    : { text: "Relay OK", cls: "text-emerald-700 dark:text-emerald-300", icon: "check" as IconName };
                return (
                  <li key={gate.id} className="flex items-center justify-between gap-3 px-5 py-3">
                    <div className="flex min-w-0 items-center gap-3">
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface-3 text-body">
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
      </div>

      {/* Gate and device health: for the site team, not the guardhouse. */}
      {isAdmin && (
        <>
          <h2 className="mb-3 mt-8 text-sm font-semibold uppercase tracking-wider text-muted">Gates &amp; devices</h2>
          <div className="grid grid-cols-2 gap-3 sm:gap-5 xl:grid-cols-4">
            <Kpi label="Entries granted today" value={s?.granted_today ?? "–"} icon="check" href="/access/"
              footer={s && decided ? `${Math.round((s.granted_today / decided) * 100)}% of ${decided} gate decisions` : "No gate decisions yet today"} />
            <Kpi label="Denied today" value={s?.denied_today ?? "–"} icon="shield" href="/access/"
              footer={s && <StatusLine ok={!s.errors_today} okText="No relay errors" badText={`${s.errors_today} relay error${s.errors_today === 1 ? "" : "s"}`} />} />
            <Kpi label="Invitations valid today" value={s?.invitations_today ?? "–"} icon="ticket" href="/invitations/"
              footer={s && (s.open_calls ? <StatusLine ok={false} okText="" badText={`${s.open_calls} intercom call${s.open_calls === 1 ? "" : "s"} ringing`} /> : "Visitors expected by invitation")} />
            <Kpi label="Devices online" value={s ? `${devicesTotal - deviceIssues}/${devicesTotal}` : "–"} icon="cpu" href="/setup/devices/"
              footer={s && (devicesTotal ? <StatusLine ok={!deviceIssues} okText="All devices healthy" badText={`${deviceIssues} need${deviceIssues === 1 ? "s" : ""} attention`} /> : "No devices configured")} />
          </div>
          <div className="mt-5 grid items-start gap-5 xl:grid-cols-3">
            <Card className="xl:col-span-2">
              <CardHeader title="Gate traffic today" action={<span className="text-xs text-muted">Gate decisions per hour (SGT)</span>} />
              <div className="p-5">{s ? <TrafficChart data={s.hourly} nowHour={nowHour} /> : <Loading />}</div>
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
        </>
      )}
      <ConfirmDialog open={!!leaving} title="Check out visitor" confirmLabel="Check out"
        message={leaving && <>Check out <strong>{leaving.visitor_name}</strong> ({leaving.pass_number}, {leaving.unit_display})?</>}
        onConfirm={async () => {
          await api(`/v1/visits/${leaving!.id}/check_out/`, { method: "POST" });
          toast("success", `${leaving!.pass_number} checked out.`);
          inside.mutate();
          summary.mutate();
        }}
        onClose={() => setLeaving(null)} />
      <OpenGateDialog gate={opening} onClose={() => setOpening(null)} />
    </>
  );
}
