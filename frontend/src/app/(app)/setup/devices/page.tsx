"use client";

import { useState } from "react";
import useSWR, { type KeyedMutator } from "swr";

import { useGates } from "@/components/bits";
import { ConfirmDialog, CopyField, EntityModal, type FieldDef, type Option, remove, Tabs } from "@/components/forms";
import { Icon } from "@/components/icons";
import { Badge, Button, Card, Empty, Loading, Modal, PageHeader, Table, Td, Th, useToast } from "@/components/ui";
import { api, ApiError, query } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { Camera, Gate, IntegrationAccount, Kiosk, Page, Relay } from "@/lib/types";

type Tab = "gates" | "relays" | "cameras" | "kiosks" | "accounts";

const isOnline = (iso: string | null, minutes: number) => !!iso && Date.now() - new Date(iso).getTime() < minutes * 60_000;
const DIRECTIONS: Option[] = [{ value: "entry", label: "Entry" }, { value: "exit", label: "Exit" }, { value: "both", label: "Entry & exit" }];

export default function DevicesSetupPage() {
  const { condo, isAdmin } = useSession();
  const [tab, setTab] = useState<Tab>(() => {
    if (typeof window === "undefined") return "gates";
    const t = new URLSearchParams(window.location.search).get("tab");
    return (["gates", "relays", "cameras", "kiosks", "accounts"].includes(t ?? "") ? t : "gates") as Tab;
  });
  const gates = useGates(condo.id);
  const relays = useSWR<Page<Relay>>(isAdmin ? `/v1/relays/${query({ gate__condominium: condo.id, page_size: 200 })}` : null);
  const cameras = useSWR<Page<Camera>>(isAdmin ? `/v1/cameras/${query({ gate__condominium: condo.id, page_size: 200 })}` : null);
  const kiosks = useSWR<Page<Kiosk>>(isAdmin ? `/v1/kiosks/${query({ condominium: condo.id, page_size: 200 })}` : null);
  const accounts = useSWR<Page<IntegrationAccount>>(isAdmin ? `/v1/integration-accounts/${query({ condominium: condo.id, page_size: 200 })}` : null);

  if (!isAdmin) return <Card><Empty>Gates and devices are managed by the condo admin.</Empty></Card>;

  const gateOptions: Option[] = (gates.data?.results ?? []).map((g) => ({ value: g.id, label: g.name }));
  const gateName = (id: number | null) => gates.data?.results.find((g) => g.id === id)?.name ?? "—";
  const select = (t: Tab) => {
    setTab(t);
    window.history.replaceState(null, "", `?tab=${t}`);
  };

  return (
    <>
      <PageHeader title="Gates & devices" description="Gates, the relays that open them, LPR cameras, visitor kiosks and the cloud accounts behind the relays." />
      <Card>
        <Tabs
          active={tab}
          onChange={select}
          tabs={[
            { key: "gates", label: "Gates", count: gates.data?.count },
            { key: "relays", label: "Relays", count: relays.data?.count },
            { key: "cameras", label: "LPR cameras", count: cameras.data?.count },
            { key: "kiosks", label: "Kiosks", count: kiosks.data?.count },
            { key: "accounts", label: "Cloud accounts", count: accounts.data?.count },
          ]}
        />
        {tab === "gates" && <GatesTab condoId={condo.id} data={gates.data} mutate={gates.mutate} />}
        {tab === "relays" && <RelaysTab data={relays.data} mutate={relays.mutate} gateOptions={gateOptions} gateName={gateName} accounts={accounts.data?.results ?? []} />}
        {tab === "cameras" && <CamerasTab data={cameras.data} mutate={cameras.mutate} gateOptions={gateOptions} gateName={gateName} />}
        {tab === "kiosks" && <KiosksTab condoId={condo.id} data={kiosks.data} mutate={kiosks.mutate} gateOptions={gateOptions} gateName={gateName} />}
        {tab === "accounts" && <AccountsTab condoId={condo.id} data={accounts.data} mutate={accounts.mutate} />}
      </Card>
    </>
  );
}

function Toolbar({ text, onAdd, addLabel, disabled }: { text: string; onAdd: () => void; addLabel: string; disabled?: string }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
      <p className="max-w-2xl text-sm text-muted">{disabled ?? text}</p>
      <Button variant="primary" onClick={onAdd} disabled={!!disabled}><Icon name="plus" className="h-4 w-4" /> {addLabel}</Button>
    </div>
  );
}

function RowActions({ onEdit, onDelete, children }: { onEdit: () => void; onDelete: () => void; children?: React.ReactNode }) {
  return (
    <Td className="whitespace-nowrap text-right">
      {children}
      <Button size="sm" variant="ghost" onClick={onEdit}>Edit</Button>
      <Button size="sm" variant="ghost" onClick={onDelete}>Delete</Button>
    </Td>
  );
}

// --- Gates -------------------------------------------------------------------

const gateFields: FieldDef[] = [
  { name: "name", label: "Name", required: true, placeholder: "Main gate", wide: true },
  { name: "gate_type", label: "Type", type: "select", required: true, options: [
    { value: "vehicle", label: "Vehicle barrier" }, { value: "pedestrian", label: "Pedestrian gate" }, { value: "door", label: "Door" }] },
  { name: "direction", label: "Direction", type: "select", required: true, options: DIRECTIONS },
  { name: "lpr_auto_open_residents", label: "Auto-open for resident plates", type: "checkbox", wide: true },
  { name: "lpr_auto_open_invited", label: "Auto-open for plates on a valid invitation", type: "checkbox", wide: true },
  { name: "is_active", label: "Active", type: "checkbox" },
];

function GatesTab({ condoId, data, mutate }: { condoId: number; data?: Page<Gate>; mutate: KeyedMutator<Page<Gate>> }) {
  const [editing, setEditing] = useState<Gate | "new" | null>(null);
  const [deleting, setDeleting] = useState<Gate | null>(null);
  return (
    <>
      <Toolbar text="Every entrance or door that can be opened. Relays, cameras and kiosks are attached to a gate." onAdd={() => setEditing("new")} addLabel="Add gate" />
      {!data ? <Loading /> : data.results.length === 0 ? <Empty>No gates yet. Start here.</Empty> : (
        <Table>
          <thead><tr><Th>Name</Th><Th>Type</Th><Th>Direction</Th><Th>Plate auto-open</Th><Th>Status</Th><Th /></tr></thead>
          <tbody className="divide-y divide-line">
            {data.results.map((g) => (
              <tr key={g.id}>
                <Td className="font-medium text-ink">{g.name}</Td>
                <Td className="capitalize">{g.gate_type}</Td>
                <Td className="capitalize">{g.direction}</Td>
                <Td>{[g.lpr_auto_open_residents && "Residents", g.lpr_auto_open_invited && "Invited"].filter(Boolean).join(", ") || "Off"}</Td>
                <Td>{g.is_active ? <Badge tone="green">Active</Badge> : <Badge>Disabled</Badge>}</Td>
                <RowActions onEdit={() => setEditing(g)} onDelete={() => setDeleting(g)} />
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      {editing && (
        <EntityModal title={editing === "new" ? "Add gate" : `Edit ${editing.name}`} fields={gateFields} record={editing === "new" ? null : editing}
          defaults={{ gate_type: "vehicle", direction: "both", is_active: true, lpr_auto_open_residents: true, lpr_auto_open_invited: true }}
          endpoint={editing === "new" ? "/v1/gates/" : `/v1/gates/${editing.id}/`} extra={{ condominium: condoId }}
          onClose={() => setEditing(null)} onSaved={() => { setEditing(null); mutate(); }} />
      )}
      <ConfirmDialog open={!!deleting} title="Delete gate?" confirmLabel="Delete gate" onClose={() => setDeleting(null)}
        message={<>Delete <strong>{deleting?.name}</strong> together with its relays and cameras? Past access-log entries are kept.</>}
        onConfirm={async () => { await remove(`/v1/gates/${deleting!.id}/`); mutate(); }} />
    </>
  );
}

// --- Relays ------------------------------------------------------------------

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

function RelaysTab({ data, mutate, gateOptions, gateName, accounts }: {
  data?: Page<Relay>; mutate: KeyedMutator<Page<Relay>>; gateOptions: Option[]; gateName: (id: number) => string; accounts: IntegrationAccount[];
}) {
  const toast = useToast();
  const [editing, setEditing] = useState<Relay | "new" | null>(null);
  const [deleting, setDeleting] = useState<Relay | null>(null);
  const [testing, setTesting] = useState<Relay | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function command(relay: Relay, action: "test" | "check") {
    setBusy(`${relay.id}-${action}`);
    try {
      const result = await api<{ ok: boolean; via: string; detail: string }>(`/v1/relays/${relay.id}/${action}/`, { method: "POST" });
      toast("success", `${relay.name}: OK via ${result.via}${result.detail ? ` (${result.detail})` : ""}`);
    } catch (error) {
      const detail = error instanceof ApiError && error.data && typeof error.data === "object" ? (error.data as { detail?: string }).detail : undefined;
      toast("error", `${relay.name}: ${detail ?? (error as Error).message}`);
    } finally {
      setBusy(null);
      mutate();
    }
  }

  return (
    <>
      <Toolbar text="Shelly or Sonoff switches wired to the gate motor. Use Test to pulse one now." onAdd={() => setEditing("new")} addLabel="Add relay" disabled={gateOptions.length ? undefined : "Add a gate first."} />
      {!data ? <Loading /> : data.results.length === 0 ? <Empty>No relays yet.</Empty> : (
        <Table>
          <thead><tr><Th>Name</Th><Th>Gate</Th><Th>Device</Th><Th>Via</Th><Th>Last triggered</Th><Th>Status</Th><Th /></tr></thead>
          <tbody className="divide-y divide-line">
            {data.results.map((r) => (
              <tr key={r.id}>
                <Td className="font-medium text-ink">{r.name}</Td>
                <Td>{gateName(r.gate)}</Td>
                <Td>{r.provider === "shelly" ? "Shelly" : "eWeLink"}</Td>
                <Td>{{ cloud: "Cloud", local: "LAN", local_then_cloud: "LAN → cloud" }[r.control_mode]}{r.local_ip && r.control_mode !== "cloud" ? ` · ${r.local_ip}` : ""}</Td>
                <Td>{timeAgo(r.last_triggered_at)}</Td>
                <Td>
                  {!r.is_active ? <Badge>Disabled</Badge> : r.last_error ? (
                    <div title={r.last_error}><Badge tone="red">Error</Badge><div className="mt-1 max-w-xs text-xs text-rose-600 dark:text-rose-400">{r.last_error}</div></div>
                  ) : <Badge tone="green">OK</Badge>}
                </Td>
                <RowActions onEdit={() => setEditing(r)} onDelete={() => setDeleting(r)}>
                  <Button size="sm" variant="ghost" busy={busy === `${r.id}-check`} onClick={() => command(r, "check")}>Status</Button>
                  <Button size="sm" variant="ghost" onClick={() => setTesting(r)}>Test</Button>
                </RowActions>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      {editing && (
        <EntityModal wide title={editing === "new" ? "Add relay" : `Edit ${editing.name}`} fields={relayFields(gateOptions, accounts)} record={editing === "new" ? null : editing}
          defaults={{ provider: "shelly", control_mode: "cloud", pulse_seconds: 3, channel: 0, is_active: true, local_username: "admin" }}
          endpoint={editing === "new" ? "/v1/relays/" : `/v1/relays/${editing.id}/`}
          onClose={() => setEditing(null)} onSaved={() => { setEditing(null); mutate(); }} />
      )}
      <Modal open={!!testing} onClose={() => setTesting(null)} title={`Test ${testing?.name ?? ""}`}
        footer={<><Button onClick={() => setTesting(null)}>Cancel</Button><Button variant="primary" busy={busy === `${testing?.id}-test`} onClick={async () => { await command(testing!, "test"); setTesting(null); }}>Pulse now</Button></>}>
        <p className="text-sm text-body">This really opens <strong>{testing && gateName(testing.gate)}</strong>. Test pulses are not written to the access log.</p>
      </Modal>
      <ConfirmDialog open={!!deleting} title="Delete relay?" confirmLabel="Delete relay" onClose={() => setDeleting(null)}
        message={<>Delete <strong>{deleting?.name}</strong>? The gate cannot be opened remotely without a relay.</>}
        onConfirm={async () => { await remove(`/v1/relays/${deleting!.id}/`); mutate(); }} />
    </>
  );
}

// --- Cameras -----------------------------------------------------------------

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

function CamerasTab({ data, mutate, gateOptions, gateName }: { data?: Page<Camera>; mutate: KeyedMutator<Page<Camera>>; gateOptions: Option[]; gateName: (id: number) => string }) {
  const [editing, setEditing] = useState<Camera | "new" | null>(null);
  const [deleting, setDeleting] = useState<Camera | null>(null);
  const [inspecting, setInspecting] = useState<Camera | null>(null);
  return (
    <>
      <Toolbar text="Dahua cameras post plate reads to the webhook. Whether reads open gates is set by 'Licence-plate recognition' in Site settings." onAdd={() => setEditing("new")} addLabel="Add camera" disabled={gateOptions.length ? undefined : "Add a gate first."} />
      {!data ? <Loading /> : data.results.length === 0 ? <Empty>No cameras yet.</Empty> : (
        <Table>
          <thead><tr><Th>Name</Th><Th>Gate</Th><Th>Device ID</Th><Th>Direction</Th><Th>Last event</Th><Th>Status</Th><Th /></tr></thead>
          <tbody className="divide-y divide-line">
            {data.results.map((c) => (
              <tr key={c.id}>
                <Td className="font-medium text-ink">{c.name}</Td>
                <Td>{gateName(c.gate)}</Td>
                <Td className="font-mono text-xs">{c.device_id}</Td>
                <Td className="capitalize">{c.direction}</Td>
                <Td>{timeAgo(c.last_seen_at)}</Td>
                <Td>{!c.is_active ? <Badge>Disabled</Badge> : isOnline(c.last_seen_at, 24 * 60) ? <Badge tone="green">Seen today</Badge> : <Badge tone="amber">No events 24 h</Badge>}</Td>
                <RowActions onEdit={() => setEditing(c)} onDelete={() => setDeleting(c)}>
                  <Button size="sm" variant="ghost" onClick={() => setInspecting(c)}>Setup info</Button>
                </RowActions>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      {editing && (
        <EntityModal wide title={editing === "new" ? "Add LPR camera" : `Edit ${editing.name}`} fields={cameraFields(gateOptions, editing === "new")} record={editing === "new" ? null : editing}
          defaults={{ direction: "entry", is_active: true }}
          endpoint={editing === "new" ? "/v1/cameras/" : `/v1/cameras/${editing.id}/`}
          onClose={() => setEditing(null)} onSaved={() => { setEditing(null); mutate(); }} />
      )}
      <Modal wide open={!!inspecting} onClose={() => setInspecting(null)} title={`${inspecting?.name ?? ""}: camera setup`}>
        {inspecting && (
          <div className="space-y-4 text-sm">
            <p className="text-body">In the camera web page, open <em>Event &gt; ITC / HTTP upload</em> and enter:</p>
            <div><div className="mb-1 font-medium text-ink">Upload URL</div><CopyField value={inspecting.webhook_url} /></div>
            <div><div className="mb-1 font-medium text-ink">Username</div><CopyField value={inspecting.webhook_username} /></div>
            <p className="text-muted">Password: the webhook password set for this camera. Method: POST, body JSON.</p>
            <div>
              <div className="mb-1 font-medium text-ink">Last payload received {inspecting.last_seen_at && <span className="font-normal text-muted">({timeAgo(inspecting.last_seen_at)})</span>}</div>
              {inspecting.last_payload ? (
                <pre className="max-h-80 overflow-auto rounded-md bg-slate-900 p-3 text-xs text-slate-100">{JSON.stringify(inspecting.last_payload, null, 2)}</pre>
              ) : <p className="text-muted">Nothing received yet.</p>}
            </div>
          </div>
        )}
      </Modal>
      <ConfirmDialog open={!!deleting} title="Delete camera?" confirmLabel="Delete camera" onClose={() => setDeleting(null)}
        message={<>Delete <strong>{deleting?.name}</strong>? Its webhook login stops working immediately.</>}
        onConfirm={async () => { await remove(`/v1/cameras/${deleting!.id}/`); mutate(); }} />
    </>
  );
}

// --- Kiosks ------------------------------------------------------------------

function KiosksTab({ condoId, data, mutate, gateOptions, gateName }: { condoId: number; data?: Page<Kiosk>; mutate: KeyedMutator<Page<Kiosk>>; gateOptions: Option[]; gateName: (id: number | null) => string }) {
  const [editing, setEditing] = useState<Kiosk | "new" | null>(null);
  const [deleting, setDeleting] = useState<Kiosk | null>(null);
  const [regenerating, setRegenerating] = useState<Kiosk | null>(null);
  const [token, setToken] = useState<{ kiosk: string; token: string } | null>(null);
  const fields: FieldDef[] = [
    { name: "name", label: "Name", required: true, placeholder: "Lobby kiosk" },
    { name: "gate", label: "Opens gate", type: "select", options: gateOptions, hint: "The gate that opens when a resident approves a call from this kiosk." },
    { name: "is_active", label: "Active", type: "checkbox" },
  ];
  return (
    <>
      <Toolbar text="Tablets at the gate: visitors call residents or scan their invitation QR. On the tablet, open /kiosk/ on this site and enter the device token." onAdd={() => setEditing("new")} addLabel="Add kiosk" />
      {!data ? <Loading /> : data.results.length === 0 ? <Empty>No kiosks yet.</Empty> : (
        <Table>
          <thead><tr><Th>Name</Th><Th>Gate</Th><Th>Token</Th><Th>App</Th><Th>Last seen</Th><Th>Status</Th><Th /></tr></thead>
          <tbody className="divide-y divide-line">
            {data.results.map((k) => (
              <tr key={k.id}>
                <Td className="font-medium text-ink">{k.name}</Td>
                <Td>{gateName(k.gate)}</Td>
                <Td className="font-mono text-xs">{k.token_hint ? `…${k.token_hint}` : "—"}</Td>
                <Td>{k.app_version || "—"}</Td>
                <Td>{timeAgo(k.last_seen_at)}</Td>
                <Td>{!k.is_active ? <Badge>Disabled</Badge> : isOnline(k.last_seen_at, 5) ? <Badge tone="green">Online</Badge> : <Badge tone="red">Offline</Badge>}</Td>
                <RowActions onEdit={() => setEditing(k)} onDelete={() => setDeleting(k)}>
                  <Button size="sm" variant="ghost" onClick={() => setRegenerating(k)}>New token</Button>
                </RowActions>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      {editing && (
        <EntityModal<Kiosk & { token?: string }> title={editing === "new" ? "Add kiosk" : `Edit ${editing.name}`} fields={fields} record={editing === "new" ? null : editing}
          defaults={{ is_active: true }} endpoint={editing === "new" ? "/v1/kiosks/" : `/v1/kiosks/${editing.id}/`} extra={{ condominium: condoId }}
          onClose={() => setEditing(null)}
          onSaved={(saved) => { setEditing(null); mutate(); if (saved.token) setToken({ kiosk: saved.name, token: saved.token }); }} />
      )}
      <ConfirmDialog open={!!regenerating} title="Issue a new device token?" confirmLabel="Issue new token" onClose={() => setRegenerating(null)}
        message={<>The tablet <strong>{regenerating?.name}</strong> is signed out until you enter the new token on it.</>}
        onConfirm={async () => {
          const result = await api<{ token: string }>(`/v1/kiosks/${regenerating!.id}/regenerate_token/`, { method: "POST" });
          setToken({ kiosk: regenerating!.name, token: result.token });
          mutate();
        }} />
      <Modal open={!!token} onClose={() => setToken(null)} title={`Device token for ${token?.kiosk ?? ""}`} footer={<Button variant="primary" onClick={() => setToken(null)}>I have copied it</Button>}>
        {token && (
          <div className="space-y-3 text-sm">
            <p className="text-body">On the tablet, open this address and enter the token. It is shown <strong>only once</strong>.</p>
            <CopyField value={`${typeof window !== "undefined" ? window.location.origin : ""}/kiosk/`} mono={false} />
            <CopyField value={token.token} />
          </div>
        )}
      </Modal>
      <ConfirmDialog open={!!deleting} title="Delete kiosk?" confirmLabel="Delete kiosk" onClose={() => setDeleting(null)}
        message={<>Delete <strong>{deleting?.name}</strong>? The tablet is signed out immediately.</>}
        onConfirm={async () => { await remove(`/v1/kiosks/${deleting!.id}/`); mutate(); }} />
    </>
  );
}

// --- Cloud accounts ----------------------------------------------------------

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

function AccountsTab({ condoId, data, mutate }: { condoId: number; data?: Page<IntegrationAccount>; mutate: KeyedMutator<Page<IntegrationAccount>> }) {
  const [editing, setEditing] = useState<IntegrationAccount | "new" | null>(null);
  const [deleting, setDeleting] = useState<IntegrationAccount | null>(null);
  return (
    <>
      <Toolbar text="Shelly Cloud and eWeLink logins used by cloud-controlled relays. Keys are stored encrypted and never shown again." onAdd={() => setEditing("new")} addLabel="Add account" />
      {!data ? <Loading /> : data.results.length === 0 ? <Empty>No cloud accounts yet.</Empty> : (
        <Table>
          <thead><tr><Th>Label</Th><Th>Provider</Th><Th>Details</Th><Th>Credentials</Th><Th>Status</Th><Th /></tr></thead>
          <tbody className="divide-y divide-line">
            {data.results.map((a) => (
              <tr key={a.id}>
                <Td className="font-medium text-ink">{a.label}</Td>
                <Td>{a.provider === "shelly" ? "Shelly Cloud" : "eWeLink"}</Td>
                <Td className="text-xs">{a.provider === "shelly" ? a.shelly_server_uri || "—" : `Region ${a.ewelink_region} · ${a.ewelink_account || "no login"}`}</Td>
                <Td>{(a.provider === "shelly" ? a.has_shelly_auth_key : a.has_ewelink_app_secret) ? <Badge tone="green">Saved</Badge> : <Badge tone="amber">Missing</Badge>}</Td>
                <Td>{a.is_active ? <Badge tone="green">Active</Badge> : <Badge>Disabled</Badge>}</Td>
                <RowActions onEdit={() => setEditing(a)} onDelete={() => setDeleting(a)} />
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      {editing && (
        <EntityModal wide title={editing === "new" ? "Add cloud account" : `Edit ${editing.label}`} fields={accountFields} record={editing === "new" ? null : (editing as unknown as Record<string, unknown>)}
          defaults={{ provider: "shelly", ewelink_region: "as", is_active: true }}
          endpoint={editing === "new" ? "/v1/integration-accounts/" : `/v1/integration-accounts/${editing.id}/`} extra={{ condominium: condoId }}
          onClose={() => setEditing(null)} onSaved={() => { setEditing(null); mutate(); }} />
      )}
      <ConfirmDialog open={!!deleting} title="Delete cloud account?" confirmLabel="Delete account" onClose={() => setDeleting(null)}
        message={<>Delete <strong>{deleting?.label}</strong>? Relays still using it must be moved first.</>}
        onConfirm={async () => { await remove(`/v1/integration-accounts/${deleting!.id}/`); mutate(); }} />
    </>
  );
}
