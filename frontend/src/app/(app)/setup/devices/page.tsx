"use client";

import { useState } from "react";
import useSWR, { type KeyedMutator } from "swr";

import { useGates } from "@/components/bits";
import { ConfirmDialog, CopyField, EntityModal, type FieldDef, type Option, remove } from "@/components/forms";
import { Icon, type IconName } from "@/components/icons";
import { ComingSoon, upsellText, useModuleCatalogue } from "@/components/ModuleGate";
import { Badge, Button, Card, Empty, Loading, Modal, PageHeader, type Tone, useToast } from "@/components/ui";
import { api, ApiError, query } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Camera, Gate, IntegrationAccount, Kiosk, Page, Relay } from "@/lib/types";

const isOnline = (iso: string | null, minutes: number) => !!iso && Date.now() - new Date(iso).getTime() < minutes * 60_000;
const DIRECTIONS: Option[] = [{ value: "entry", label: "Entry" }, { value: "exit", label: "Exit" }, { value: "both", label: "Entry & exit" }];
const GATE_TYPE: Record<Gate["gate_type"], string> = { vehicle: "Car barrier", pedestrian: "Pedestrian gate", door: "Door" };
const DIRECTION: Record<Gate["direction"], string> = { entry: "entry only", exit: "exit only", both: "entry and exit" };

type State = { tone: Tone; label: string; note?: string };
const relayState = (r: Relay): State => !r.is_active ? { tone: "slate", label: "Switched off" }
  : r.last_error ? { tone: "red", label: "Problem", note: r.last_error } : { tone: "green", label: "Working" };
const cameraState = (c: Camera): State => !c.is_active ? { tone: "slate", label: "Switched off" }
  : isOnline(c.last_seen_at, 24 * 60) ? { tone: "green", label: "Reading plates" } : { tone: "amber", label: "No plates in 24 h" };
const kioskState = (k: Kiosk): State => !k.is_active ? { tone: "slate", label: "Switched off" }
  : isOnline(k.last_seen_at, 5) ? { tone: "green", label: "Online" } : { tone: "red", label: "Offline" };

const VIEWS = ["gates", "relays", "cameras", "kiosks", "accounts"] as const;
type View = (typeof VIEWS)[number];

type Dialog =
  | { kind: "gate"; record: Gate | null }
  | { kind: "relay"; record: Relay | null; gate?: number }
  | { kind: "camera"; record: Camera | null; gate?: number }
  | { kind: "kiosk"; record: Kiosk | null; gate?: number }
  | { kind: "account"; record: IntegrationAccount | null }
  | { kind: "test"; relay: Relay }
  | { kind: "setup"; camera: Camera }
  | { kind: "token"; kiosk: Kiosk }
  | { kind: "delete"; what: string; name: string; endpoint: string; message: string }
  | { kind: "soon"; module: string; points: string[] };

const SOON = {
  face_terminal: [
    "Residents enter by face at Hikvision access terminals, no card needed.",
    "Faces are added from the resident app or the dashboard, with the resident's consent.",
    "Removed from the terminals automatically when a resident moves out.",
  ],
  local_devices: [
    "A secure link from Elix to the devices at your site, without opening your router.",
    "Relays answer faster and keep working when the relay maker's cloud is down.",
    "Plates and faces stay on the cameras and terminals, so gates keep working if the internet drops.",
  ],
};

// --- Forms ------------------------------------------------------------------------------------------------

const gateFields: FieldDef[] = [
  { name: "name", label: "Name", required: true, placeholder: "Main gate", wide: true },
  { name: "gate_type", label: "Type", type: "select", required: true, options: [
    { value: "vehicle", label: "Vehicle barrier" }, { value: "pedestrian", label: "Pedestrian gate" }, { value: "door", label: "Door" }] },
  { name: "direction", label: "Direction", type: "select", required: true, options: DIRECTIONS },
  { name: "lpr_auto_open_residents", label: "Auto-open for resident plates", type: "checkbox", wide: true },
  { name: "lpr_auto_open_invited", label: "Auto-open for plates on a valid invitation", type: "checkbox", wide: true },
  { name: "resident_remote_open", label: "Residents can open this gate from the app", type: "checkbox", wide: true,
    hint: "Shows the gate under Access in the resident app. Every opening is logged with the resident and unit." },
  { name: "is_active", label: "Active", type: "checkbox" },
];
function relayFields(gateOptions: Option[], accounts: IntegrationAccount[]): FieldDef[] {
  const cloud = (v: Record<string, unknown>) => v.control_mode !== "local";
  const local = (v: Record<string, unknown>) => v.control_mode !== "cloud";
  return [
    { name: "gate", label: "Gate", type: "select", required: true, options: gateOptions },
    { name: "name", label: "Name", required: true, placeholder: "Barrier relay" },
    { name: "provider", label: "Device", type: "select", required: true, options: [{ value: "shelly", label: "Shelly" }, { value: "ewelink", label: "Sonoff (eWeLink)" }] },
    { name: "control_mode", label: "Control via", type: "select", required: true, options: [
      { value: "cloud", label: "Cloud API" }, { value: "local", label: "Local LAN" }, { value: "local_then_cloud", label: "Local LAN, fall back to cloud" }] },
    { name: "pulse_seconds", label: "Pulse length (seconds)", type: "number", hint: "Match the device's Inching / Auto-off time." },
    { name: "is_active", label: "Active", type: "checkbox" },
    { name: "account", label: "Cloud account", type: "select", section: "Cloud", show: cloud,
      options: accounts.map((a) => ({ value: a.id, label: `${a.label} (${a.provider === "shelly" ? "Shelly" : "eWeLink"})` })),
      hint: accounts.length ? undefined : "Add one on the Cloud accounts tab first." },
    { name: "cloud_device_id", label: "Device ID", show: cloud, hint: "Shelly: Settings > Device information. eWeLink: device ID such as 1000abc123." },
    { name: "channel", label: "Channel", type: "number", show: cloud, hint: "0 for single-channel devices." },
    { name: "local_ip", label: "LAN IP address", section: "Local LAN", show: local, nullable: true, placeholder: "192.168.1.22", hint: "The server must be able to reach this address (e.g. over Tailscale)." },
    { name: "local_port", label: "Port", type: "number", show: local, hint: "Shelly 80, eWeLink LAN 8081." },
    { name: "local_username", label: "Username", show: (v) => local(v) && v.provider === "shelly", placeholder: "admin" },
    { name: "local_password", label: "Password", type: "secret", show: (v) => local(v) && v.provider === "shelly" },
    { name: "local_device_key", label: "eWeLink device key", type: "secret", show: (v) => local(v) && v.provider === "ewelink", hint: "Only for eWeLink LAN mode with encryption." },
  ];
}
function cameraFields(gateOptions: Option[], creating: boolean): FieldDef[] {
  return [
    { name: "gate", label: "Gate", type: "select", required: true, options: gateOptions },
    { name: "name", label: "Name", required: true, placeholder: "Entry LPR" },
    { name: "device_id", label: "Dahua device ID", required: true, hint: "The deviceID the camera sends in its PlateResult event." },
    { name: "direction", label: "Direction", type: "select", required: true, options: DIRECTIONS, hint: "Exit cameras open the gate but never use up an invitation entry." },
    { name: "ip_address", label: "Camera IP (optional)", nullable: true },
    { name: "is_active", label: "Active", type: "checkbox" },
    { name: "webhook_username", label: "Webhook username", required: true, section: "Camera HTTP upload login", hint: "Enter in the camera's HTTP upload settings." },
    { name: "webhook_password", label: "Webhook password", type: "secret", required: creating, hint: creating ? "At least 8 characters." : "Leave blank to keep the current one." },
    { name: "plate_field", label: "Plate field path (advanced)", wide: true, placeholder: "Picture.Plate.PlateNumber", hint: "Leave blank to detect common Dahua formats." },
    { name: "api_username", label: "Camera API username", section: "Camera API (optional, for snapshots)" },
    { name: "api_password", label: "Camera API password", type: "secret" },
  ];
}
const accountFields: FieldDef[] = [
  { name: "provider", label: "Provider", type: "select", required: true, options: [{ value: "shelly", label: "Shelly Cloud" }, { value: "ewelink", label: "eWeLink (Sonoff)" }] },
  { name: "label", label: "Label", required: true, placeholder: "Main Shelly account" },
  { name: "is_active", label: "Active", type: "checkbox" },
  { name: "shelly_server_uri", label: "Server URI", type: "url", wide: true, section: "Shelly Cloud", show: (v) => v.provider === "shelly",
    placeholder: "https://shelly-103-eu.shelly.cloud", hint: "Shelly app > User settings > Authorization cloud key." },
  { name: "shelly_auth_key", label: "Auth key", type: "secret", wide: true, show: (v) => v.provider === "shelly" },
  { name: "ewelink_region", label: "Region", type: "select", section: "eWeLink", show: (v) => v.provider === "ewelink",
    options: [{ value: "as", label: "Asia" }, { value: "eu", label: "Europe" }, { value: "us", label: "Americas" }, { value: "cn", label: "China" }] },
  { name: "ewelink_app_id", label: "App ID", show: (v) => v.provider === "ewelink", hint: "From dev.ewelink.cc" },
  { name: "ewelink_app_secret", label: "App secret", type: "secret", show: (v) => v.provider === "ewelink" },
  { name: "ewelink_account", label: "Login (email or phone)", show: (v) => v.provider === "ewelink", hint: "Lets the server sign in again if tokens expire." },
  { name: "ewelink_password", label: "Password", type: "secret", show: (v) => v.provider === "ewelink" },
  { name: "ewelink_access_token", label: "Access token", type: "secret", show: (v) => v.provider === "ewelink", hint: "Optional if login and password are set." },
  { name: "ewelink_refresh_token", label: "Refresh token", type: "secret", show: (v) => v.provider === "ewelink" },
  { name: "notes", label: "Notes", type: "textarea" },
];

// --- Building blocks -----------------------------------------------------------------------------------

function DeviceRow({ icon, title, detail, state, children }: { icon: IconName; title: string; detail: string; state: State; children?: React.ReactNode }) {
  return (
    <li className="flex items-start gap-3 py-3">
      <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface-3 text-body"><Icon name={icon} className="h-5 w-5" /></span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium text-ink">{title}</span>
          <Badge tone={state.tone}>{state.label}</Badge>
        </div>
        <div className="text-sm text-muted">{detail}</div>
        {state.note && <div className="mt-1 text-sm text-rose-600 dark:text-rose-400">{state.note}</div>}
        <div className="-ml-2 mt-2 flex flex-wrap gap-1">{children}</div>
      </div>
    </li>
  );
}

// --- Page ------------------------------------------------------------------------------------------------

export default function DevicesSetupPage() {
  const { condo, isAdmin } = useSession();
  const toast = useToast();
  const catalogue = useModuleCatalogue();
  const hasLpr = condo.modules?.includes("lpr") ?? false;
  const gates = useGates(condo.id);
  const relays = useSWR<Page<Relay>>(isAdmin ? `/v1/relays/${query({ gate__condominium: condo.id, page_size: 200 })}` : null);
  const cameras = useSWR<Page<Camera>>(isAdmin && hasLpr ? `/v1/cameras/${query({ gate__condominium: condo.id, page_size: 200 })}` : null);
  const kiosks = useSWR<Page<Kiosk>>(isAdmin ? `/v1/kiosks/${query({ condominium: condo.id, page_size: 200 })}` : null);
  const accounts = useSWR<Page<IntegrationAccount>>(isAdmin ? `/v1/integration-accounts/${query({ condominium: condo.id, page_size: 200 })}` : null);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [token, setToken] = useState<{ kiosk: string; token: string } | null>(null);
  const [view, setViewState] = useState<View | null>(() => {
    if (typeof window === "undefined") return null;
    const v = new URLSearchParams(window.location.search).get("view");
    return (VIEWS as readonly string[]).includes(v ?? "") ? (v as View) : null;
  });
  const setView = (v: View | null) => {
    setViewState(v);
    window.history.replaceState(null, "", v ? `?view=${v}` : window.location.pathname);
    window.scrollTo({ top: 0 });
  };

  if (!isAdmin) return <Card><Empty>Gates and devices are managed by the site admin.</Empty></Card>;
  if (!gates.data || !relays.data || !kiosks.data || !accounts.data || (hasLpr && !cameras.data)) return <Loading />;

  const gateList = gates.data.results;
  const gateOptions: Option[] = gateList.map((g) => ({ value: g.id, label: g.name }));
  const gateName = (id: number | null) => gateList.find((g) => g.id === id)?.name ?? "—";
  const relayList = relays.data.results;
  const cameraList = cameras.data?.results ?? [];
  const kioskList = kiosks.data.results;
  const accountList = accounts.data.results;
  const refresh = () => { gates.mutate(); relays.mutate(); cameras.mutate(); kiosks.mutate(); accounts.mutate(); };
  const close = () => setDialog(null);
  const saved = () => { close(); refresh(); };

  const states = [...relayList.map(relayState), ...cameraList.map(cameraState), ...kioskList.map(kioskState)];
  const bad = (x: { tone: string }) => x.tone === "red" || x.tone === "amber";
  const attention = states.filter(bad).length;
  const issueView: View | null = relayList.map(relayState).some(bad) ? "relays" : cameraList.map(cameraState).some(bad) ? "cameras"
    : kioskList.map(kioskState).some(bad) ? "kiosks" : null;
  const lprInfo = catalogue?.modules.find((m) => m.key === "lpr");

  async function command(relay: Relay, action: "test" | "check") {
    setBusy(`${relay.id}-${action}`);
    try {
      const result = await api<{ ok: boolean; via: string; detail: string }>(`/v1/relays/${relay.id}/${action}/`, { method: "POST" });
      toast("success", `${relay.name}: ${action === "test" ? "opened" : "working"} (via ${result.via})${result.detail ? `, ${result.detail}` : ""}`);
    } catch (error) {
      const detail = error instanceof ApiError && error.data && typeof error.data === "object" ? (error.data as { detail?: string }).detail : undefined;
      toast("error", `${relay.name}: ${detail ?? (error as Error).message}`);
    } finally {
      setBusy(null);
      relays.mutate();
    }
  }

  const askDelete = (what: string, name: string, endpoint: string, message: string) => setDialog({ kind: "delete", what, name, endpoint, message });

  const problems = (list: State[]) => list.filter((x) => x.tone === "red" || x.tone === "amber").length;
  const relayProblems = problems(relayList.map(relayState));
  const cameraProblems = problems(cameraList.map(cameraState));
  const kioskProblems = problems(kioskList.map(kioskState));
  const missingKeys = accountList.filter((a) => a.is_active && !(a.provider === "shelly" ? a.has_shelly_auth_key : a.has_ewelink_app_secret)).length;
  const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const gateDevices = (id: number) => [
    plural(relayList.filter((r) => r.gate === id).length, "relay"),
    ...(hasLpr ? [plural(cameraList.filter((c) => c.gate === id).length, "plate camera")] : []),
    plural(kioskList.filter((k) => k.gate === id).length, "kiosk"),
  ].join(" · ");

  const CATEGORIES: { key: View | "face_terminal" | "local_devices"; title: string; icon: IconName; what: string; badge: State; locked?: boolean; soon?: boolean }[] = [
    { key: "gates", title: "Gates", icon: "unlock", what: "Every entrance or door that can be opened, and its rules for plates and the resident app.",
      badge: gateList.length ? { tone: "green", label: plural(gateList.length, "gate") } : { tone: "amber", label: "Start here" } },
    { key: "relays", title: "Relays", icon: "zap", what: "Shelly or Sonoff switches wired to the gate motor, so a gate opens from the kiosk, the app or this dashboard.",
      badge: relayProblems ? { tone: "red", label: `${relayProblems} problem${relayProblems === 1 ? "" : "s"}` } : relayList.length ? { tone: "green", label: `${relayList.length} working` } : { tone: "amber", label: "None yet" } },
    { key: "cameras", title: "Plate cameras", icon: "camera", what: "Dahua cameras that read number plates and let residents' and invited cars in.", locked: !hasLpr,
      badge: !hasLpr ? { tone: "slate", label: "Not in plan" } : cameraProblems ? { tone: "amber", label: `${cameraProblems} quiet` } : cameraList.length ? { tone: "green", label: `${cameraList.length} reading` } : { tone: "slate", label: "None yet" } },
    { key: "kiosks", title: "Kiosks", icon: "tablet", what: "Tablets in the lobby where visitors call residents, walk in or scan their invitation.",
      badge: kioskProblems ? { tone: "red", label: `${kioskProblems} offline` } : kioskList.length ? { tone: "green", label: `${kioskList.length} online` } : { tone: "slate", label: "None yet" } },
    { key: "accounts", title: "Cloud accounts", icon: "cloud", what: "Shelly and eWeLink logins that relays use over the internet. Keys are stored encrypted.",
      badge: missingKeys ? { tone: "amber", label: `${missingKeys} key missing` } : accountList.length ? { tone: "green", label: plural(accountList.length, "account") } : { tone: "slate", label: "Optional" } },
    { key: "face_terminal", title: "Face terminals", icon: "sparkle", what: "Residents enter by face at access terminals, no card needed.", soon: true, badge: { tone: "blue", label: "Coming soon" } },
    { key: "local_devices", title: "On-site link", icon: "sparkle", what: "A secure link to the devices at your site, so gates keep working when the internet drops.", soon: true, badge: { tone: "blue", label: "Coming soon" } },
  ];
  const current = CATEGORIES.find((c) => c.key === view);

  const openCategory = (key: (typeof CATEGORIES)[number]["key"]) => {
    if (key === "face_terminal" || key === "local_devices") setDialog({ kind: "soon", module: key, points: SOON[key] });
    else setView(key);
  };
  const addNew = () => {
    if (view === "gates") setDialog({ kind: "gate", record: null });
    else if (view === "relays") setDialog({ kind: "relay", record: null });
    else if (view === "cameras") setDialog({ kind: "camera", record: null });
    else if (view === "kiosks") setDialog({ kind: "kiosk", record: null });
    else if (view === "accounts") setDialog({ kind: "account", record: null });
  };
  const ADD_LABEL: Record<View, string> = { gates: "Add gate", relays: "Add relay", cameras: "Add plate camera", kiosks: "Add kiosk", accounts: "Add account" };
  const needsGate = (view === "relays" || view === "cameras") && !gateList.length;

  const rows = (items: React.ReactNode[], empty: string) => items.length
    ? <ul className="divide-y divide-line px-5 sm:px-6">{items}</ul>
    : <Empty>{empty}</Empty>;

  return (
    <>
      {!current ? (
        <>
          <PageHeader title="Gates & devices" description="Everything that opens a gate or sees who comes. Open a card to manage it." />
          <div className={`mb-6 flex items-center gap-3 rounded-xl border px-4 py-3 text-sm ${attention ? "border-amber-500/40 bg-amber-500/10 text-amber-900 dark:text-amber-200" : "border-emerald-500/30 bg-emerald-500/10 text-emerald-900 dark:text-emerald-200"}`}>
            <Icon name={attention ? "bell" : "check"} className="h-5 w-5 shrink-0" />
            <span>
              {plural(gateList.length, "gate")} · {plural(states.length, "device")} ·{" "}
              {attention
                ? <button type="button" onClick={() => issueView && setView(issueView)} className="font-semibold underline underline-offset-2 hover:opacity-80">{attention} need{attention === 1 ? "s" : ""} attention →</button>
                : <strong>everything is working</strong>}
            </span>
          </div>
          <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
            {CATEGORIES.map((c) => (
              <Card key={c.key} className={`flex flex-col ${c.soon ? "border-dashed" : ""}`}>
                <div className="flex flex-1 flex-col p-5 sm:p-6">
                  <div className="flex items-start justify-between gap-3">
                    <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary-500/10 text-primary-600 dark:text-primary-300">
                      <Icon name={c.locked ? "lock" : c.icon} className="h-6 w-6" />
                    </span>
                    <Badge tone={c.badge.tone}>{c.badge.label}</Badge>
                  </div>
                  <h2 className="mt-4 text-lg font-semibold text-ink">{c.title}</h2>
                  <p className="mt-1 flex-1 text-sm text-body">{c.what}</p>
                  <div className="mt-5 flex flex-wrap items-center gap-2">
                    {c.locked ? <span className="text-sm text-muted">{upsellText(lprInfo)}</span>
                      : <Button variant={c.badge.label === "Start here" ? "primary" : "secondary"} onClick={() => openCategory(c.key)}>{c.soon ? "Learn more" : "Open"}</Button>}
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </>
      ) : (
        <>
          <button onClick={() => setView(null)} className="mb-4 inline-flex items-center gap-1.5 text-sm font-medium text-primary-600 hover:underline dark:text-primary-400">
            <Icon name="chevron" className="h-4 w-4 rotate-180" /> All devices
          </button>
          <PageHeader title={current.title} description={current.what}
            action={<Button variant="primary" onClick={addNew} disabled={needsGate}><Icon name="plus" className="h-4 w-4" /> {ADD_LABEL[view as View]}</Button>} />
          {needsGate && <p className="mb-4 text-sm text-muted">Add a gate first: every relay and plate camera belongs to a gate.</p>}
          <Card>
            {view === "gates" && rows(gateList.map((g) => {
              const rules = [g.lpr_auto_open_residents && "Opens for residents' plates", g.lpr_auto_open_invited && "Opens for invited plates",
                g.resident_remote_open && "Residents can open it from the app"].filter(Boolean) as string[];
              return (
                <DeviceRow key={g.id} icon="unlock" title={g.name} state={g.is_active ? { tone: "green", label: "In use" } : { tone: "slate", label: "Switched off" }}
                  detail={`${GATE_TYPE[g.gate_type] ?? g.gate_type} · ${DIRECTION[g.direction] ?? g.direction} · ${gateDevices(g.id)}`}>
                  {rules.map((r) => <span key={r} className="mr-1 rounded-full bg-primary-500/10 px-2.5 py-1 text-xs font-medium text-primary-700 dark:text-primary-300">{r}</span>)}
                  <span className="basis-full" />
                  <Button size="sm" onClick={() => setDialog({ kind: "gate", record: g })}>Edit</Button>
                  <Button size="sm" variant="ghost" onClick={() => askDelete("gate", g.name, `/v1/gates/${g.id}/`, " together with its relays and cameras? Past access-log entries are kept.")}>Delete</Button>
                </DeviceRow>
              );
            }), "No gates yet. Add one for each entrance or door that can be opened.")}
            {view === "relays" && rows(relayList.map((r) => (
              <DeviceRow key={r.id} icon="zap" title={r.name} state={relayState(r)}
                detail={`${gateName(r.gate)} · ${r.provider === "shelly" ? "Shelly" : "Sonoff (eWeLink)"} · ${{ cloud: "over the internet", local: "local network", local_then_cloud: "local network, then internet" }[r.control_mode]} · last opened ${timeAgo(r.last_triggered_at)}`}>
                <Button size="sm" onClick={() => setDialog({ kind: "test", relay: r })}>Test open</Button>
                <Button size="sm" variant="ghost" busy={busy === `${r.id}-check`} onClick={() => command(r, "check")}>Check</Button>
                <Button size="sm" variant="ghost" onClick={() => setDialog({ kind: "relay", record: r })}>Edit</Button>
                <Button size="sm" variant="ghost" onClick={() => askDelete("relay", r.name, `/v1/relays/${r.id}/`, "? The gate cannot be opened remotely without a relay.")}>Delete</Button>
              </DeviceRow>
            )), "No relays yet: gates cannot be opened remotely.")}
            {view === "cameras" && rows(cameraList.map((c) => (
              <DeviceRow key={c.id} icon="camera" title={c.name} state={cameraState(c)}
                detail={`${gateName(c.gate)} · ${{ entry: "entry", exit: "exit", both: "entry & exit" }[c.direction]} camera · last plate ${timeAgo(c.last_seen_at)}`}>
                <Button size="sm" onClick={() => setDialog({ kind: "setup", camera: c })}>Setup info</Button>
                <Button size="sm" variant="ghost" onClick={() => setDialog({ kind: "camera", record: c })}>Edit</Button>
                <Button size="sm" variant="ghost" onClick={() => askDelete("camera", c.name, `/v1/cameras/${c.id}/`, "? Its upload login stops working immediately.")}>Delete</Button>
              </DeviceRow>
            )), "No plate cameras yet.")}
            {view === "kiosks" && rows(kioskList.map((k) => (
              <DeviceRow key={k.id} icon="tablet" title={k.name} state={kioskState(k)}
                detail={`${k.gate ? `Opens ${gateName(k.gate)}` : "Not linked to a gate"} · ${k.prints_slips ? "with slip printer" : "no printer"} · last seen ${timeAgo(k.last_seen_at)}${k.app_version ? ` · ${k.app_version}` : ""}`}>
                <Button size="sm" onClick={() => setDialog({ kind: "token", kiosk: k })}>New sign-in code</Button>
                <Button size="sm" variant="ghost" onClick={() => setDialog({ kind: "kiosk", record: k })}>Edit</Button>
                <Button size="sm" variant="ghost" onClick={() => askDelete("kiosk", k.name, `/v1/kiosks/${k.id}/`, "? The tablet is signed out immediately.")}>Delete</Button>
              </DeviceRow>
            )), "No kiosks yet.")}
            {view === "accounts" && rows(accountList.map((a) => {
              const hasKey = a.provider === "shelly" ? a.has_shelly_auth_key : a.has_ewelink_app_secret;
              const state: State = !a.is_active ? { tone: "slate", label: "Switched off" } : hasKey ? { tone: "green", label: "Ready" } : { tone: "amber", label: "Key missing" };
              return (
                <DeviceRow key={a.id} icon="cloud" title={a.label} state={state}
                  detail={a.provider === "shelly" ? `Shelly Cloud · ${a.shelly_server_uri || "no server set"}` : `eWeLink · region ${a.ewelink_region.toUpperCase()}`}>
                  <Button size="sm" onClick={() => setDialog({ kind: "account", record: a })}>Edit</Button>
                  <Button size="sm" variant="ghost" onClick={() => askDelete("account", a.label, `/v1/integration-accounts/${a.id}/`, "? Relays still using it must be moved first.")}>Delete</Button>
                </DeviceRow>
              );
            }), "No cloud accounts yet. Only needed for relays that work over the internet.")}
          </Card>
        </>
      )}

      {/* --- Dialogs --- */}
      {dialog?.kind === "gate" && (
        <EntityModal title={dialog.record ? `Edit ${dialog.record.name}` : "Add gate"} fields={gateFields} record={dialog.record}
          defaults={{ gate_type: "vehicle", direction: "both", is_active: true, lpr_auto_open_residents: true, lpr_auto_open_invited: true, resident_remote_open: false }}
          endpoint={dialog.record ? `/v1/gates/${dialog.record.id}/` : "/v1/gates/"} extra={{ condominium: condo.id }} onClose={close} onSaved={saved} />
      )}
      {dialog?.kind === "relay" && (
        <EntityModal wide title={dialog.record ? `Edit ${dialog.record.name}` : `Add relay${dialog.gate ? ` to ${gateName(dialog.gate)}` : ""}`}
          fields={relayFields(gateOptions, accountList)} record={dialog.record}
          defaults={{ gate: dialog.gate, provider: "shelly", control_mode: "cloud", pulse_seconds: 3, channel: 0, is_active: true, local_username: "admin" }}
          endpoint={dialog.record ? `/v1/relays/${dialog.record.id}/` : "/v1/relays/"} onClose={close} onSaved={saved} />
      )}
      {dialog?.kind === "camera" && (
        <EntityModal wide title={dialog.record ? `Edit ${dialog.record.name}` : `Add plate camera${dialog.gate ? ` to ${gateName(dialog.gate)}` : ""}`}
          fields={cameraFields(gateOptions, !dialog.record)} record={dialog.record}
          defaults={{ gate: dialog.gate, direction: "entry", is_active: true }}
          endpoint={dialog.record ? `/v1/cameras/${dialog.record.id}/` : "/v1/cameras/"} onClose={close} onSaved={saved} />
      )}
      {dialog?.kind === "kiosk" && (
        <EntityModal<Kiosk & { token?: string }> title={dialog.record ? `Edit ${dialog.record.name}` : `Add kiosk${dialog.gate ? ` at ${gateName(dialog.gate)}` : ""}`}
          fields={kioskFields(gateOptions)} record={dialog.record}
          defaults={{ gate: dialog.gate, is_active: true, prints_slips: true }}
          endpoint={dialog.record ? `/v1/kiosks/${dialog.record.id}/` : "/v1/kiosks/"} extra={{ condominium: condo.id }} onClose={close}
          onSaved={(k) => { saved(); if (k.token) setToken({ kiosk: k.name, token: k.token }); }} />
      )}
      {dialog?.kind === "account" && (
        <EntityModal wide title={dialog.record ? `Edit ${dialog.record.label}` : "Add cloud account"} fields={accountFields}
          record={dialog.record as unknown as Record<string, unknown> | null}
          defaults={{ provider: "shelly", ewelink_region: "as", is_active: true }}
          endpoint={dialog.record ? `/v1/integration-accounts/${dialog.record.id}/` : "/v1/integration-accounts/"} extra={{ condominium: condo.id }} onClose={close} onSaved={saved} />
      )}
      <Modal open={dialog?.kind === "test"} onClose={close} title={dialog?.kind === "test" ? `Test ${dialog.relay.name}` : ""}
        footer={dialog?.kind === "test" && <><Button onClick={close}>Cancel</Button>
          <Button variant="primary" busy={busy === `${dialog.relay.id}-test`} onClick={async () => { await command(dialog.relay, "test"); close(); }}>Open now</Button></>}>
        {dialog?.kind === "test" && <p className="text-sm text-body">This really opens <strong>{gateName(dialog.relay.gate)}</strong>. Tests are not written to the access log.</p>}
      </Modal>
      <Modal wide open={dialog?.kind === "setup"} onClose={close} title={dialog?.kind === "setup" ? `${dialog.camera.name}: camera setup` : ""}>
        {dialog?.kind === "setup" && (
          <div className="space-y-4 text-sm">
            <p className="text-body">In the camera web page, open <em>Event &gt; ITC / HTTP upload</em> and enter:</p>
            <div><div className="mb-1 font-medium text-ink">Upload URL</div><CopyField value={dialog.camera.webhook_url} /></div>
            <div><div className="mb-1 font-medium text-ink">Username</div><CopyField value={dialog.camera.webhook_username} /></div>
            <p className="text-muted">Password: the upload password set for this camera. Method: POST, body JSON.</p>
            <div>
              <div className="mb-1 font-medium text-ink">Last plate data received {dialog.camera.last_seen_at && <span className="font-normal text-muted">({timeAgo(dialog.camera.last_seen_at)})</span>}</div>
              {dialog.camera.last_payload ? (
                <pre className="max-h-80 overflow-auto rounded-md bg-slate-900 p-3 text-xs text-slate-100">{JSON.stringify(dialog.camera.last_payload, null, 2)}</pre>
              ) : <p className="text-muted">Nothing received yet.</p>}
            </div>
          </div>
        )}
      </Modal>
      <ConfirmDialog open={dialog?.kind === "token"} title="Give this kiosk a new sign-in code?" confirmLabel="New code" onClose={close}
        message={dialog?.kind === "token" ? <>The tablet <strong>{dialog.kiosk.name}</strong> is signed out until you enter the new code on it.</> : null}
        onConfirm={async () => {
          if (dialog?.kind !== "token") return;
          const result = await api<{ token: string }>(`/v1/kiosks/${dialog.kiosk.id}/regenerate_token/`, { method: "POST" });
          setToken({ kiosk: dialog.kiosk.name, token: result.token });
          kiosks.mutate();
        }} />
      <Modal open={!!token} onClose={() => setToken(null)} title={`Sign-in code for ${token?.kiosk ?? ""}`} footer={<Button variant="primary" onClick={() => setToken(null)}>I have copied it</Button>}>
        {token && (
          <div className="space-y-3 text-sm">
            <p className="text-body">On the tablet, open this address and enter the code. It is shown <strong>only once</strong>.</p>
            <CopyField value={`${typeof window !== "undefined" ? window.location.origin : ""}/kiosk/`} mono={false} />
            <CopyField value={token.token} />
          </div>
        )}
      </Modal>
      <ConfirmDialog open={dialog?.kind === "delete"} title={dialog?.kind === "delete" ? `Delete ${dialog.what}?` : ""}
        confirmLabel={dialog?.kind === "delete" ? `Delete ${dialog.what}` : "Delete"} onClose={close}
        message={dialog?.kind === "delete" ? <>Delete <strong>{dialog.name}</strong>{dialog.message}</> : null}
        onConfirm={async () => { if (dialog?.kind === "delete") { await remove(dialog.endpoint); refresh(); } }} />
      <Modal wide open={dialog?.kind === "soon"} onClose={close} title="Coming soon">
        {dialog?.kind === "soon" && <ComingSoon module={dialog.module} points={dialog.points} />}
      </Modal>
    </>
  );
}

function kioskFields(gateOptions: Option[]): FieldDef[] {
  return [
    { name: "name", label: "Name", required: true, placeholder: "Lobby kiosk" },
    { name: "gate", label: "Opens gate", type: "select", options: gateOptions, hint: "The gate that opens when a resident approves a call from this kiosk." },
    { name: "prints_slips", label: "Receipt printer connected (58 mm)", type: "checkbox", wide: true,
      hint: "Walk-in slips are printed. Without a printer the pass is shown on screen for the visitor to photograph. For printing without a dialog, start Chrome with --kiosk-printing." },
    { name: "is_active", label: "Active", type: "checkbox" },
  ];
}
