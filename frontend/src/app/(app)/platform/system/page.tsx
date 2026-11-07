"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";

import { type FieldDef, FormFields, initialValues } from "@/components/forms";
import { Badge, Button, Card, CardHeader, Empty, ErrorNote, Loading, PageHeader, useToast } from "@/components/ui";
import { api, ApiError, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { SystemSettings } from "@/lib/types";

const livekitFields: FieldDef[] = [
  { name: "livekit_url", label: "LiveKit URL", wide: true, placeholder: "wss://your-project.livekit.cloud", hint: "LiveKit Cloud > Settings > Project URL." },
  { name: "livekit_api_key", label: "API key" },
  { name: "livekit_api_secret", label: "API secret", type: "secret" },
  { name: "livekit_token_ttl_seconds", label: "Room token lifetime (seconds)", type: "number", hint: "Default 600." },
  { name: "intercom_unlock_window_seconds", label: "Swipe-to-unlock window (seconds)", type: "number", hint: "How long after a call starts the gate may still be opened. Default 600." },
];
const fcmFields: FieldDef[] = [
  { name: "fcm_service_account_json", label: "Service account JSON", type: "secret-text", wide: true,
    hint: "Firebase console > Project settings > Service accounts > Generate new private key. Paste the whole file." },
];
const tuningFields: FieldDef[] = [
  { name: "relay_http_timeout", label: "Relay HTTP timeout (seconds)", type: "number", hint: "Default 5." },
  { name: "lpr_debounce_seconds", label: "Ignore repeated plate reads for (seconds)", type: "number", hint: "Default 20." },
];
const ALL = [...livekitFields, ...fcmFields, ...tuningFields];

function SourceNote({ sources, names }: { sources: SystemSettings["sources"]; names: string[] }) {
  const fromEnv = names.filter((n) => sources[n] === ".env");
  if (!fromEnv.length) return null;
  return <p className="text-xs text-muted">Blank fields fall back to the server&apos;s .env file. Currently from .env: {fromEnv.join(", ")}.</p>;
}

export default function SystemSettingsPage() {
  const { me } = useSession();
  const toast = useToast();
  const { data, mutate } = useSWR<SystemSettings>(me.is_superuser ? "/v1/system-settings/" : null);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => {
    if (data) setValues(initialValues(ALL, data as unknown as Record<string, unknown>));
  }, [data]);

  if (!me.is_superuser) return <Card><Empty>Only the platform administrator can change system settings.</Empty></Card>;
  if (!data) return <Loading />;

  const errors = error instanceof ApiError && error.data && typeof error.data === "object"
    ? Object.fromEntries(Object.entries(error.data as Record<string, unknown>).filter(([k]) => k !== "detail").map(([k, v]) => [k, errorMessage(v, "Invalid")]))
    : {};

  async function save(then?: "livekit" | "fcm") {
    setBusy(then ?? "save");
    setError(null);
    try {
      const body: Record<string, unknown> = {};
      for (const f of ALL) {
        const v = values[f.name];
        if ((f.type === "secret" || f.type === "secret-text") && v === "") continue;
        body[f.name] = f.type === "number" ? (v === "" || v === null ? null : Number(v)) : v;
      }
      await api("/v1/system-settings/", { method: "PATCH", body });
      await mutate();
      if (then) {
        const result = await api<{ ok: boolean; detail: string }>(`/v1/system-settings/test-${then}/`, { method: "POST" });
        toast(result.ok ? "success" : "error", result.detail);
      } else {
        toast("success", "System settings saved. They apply immediately.");
      }
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  const change = (n: string, v: unknown) => setValues((s) => ({ ...s, [n]: v }));
  const record = data as unknown as Record<string, unknown>;

  return (
    <>
      <PageHeader title="System settings" description="Server-wide integrations for every condominium. Secrets are stored encrypted and never shown again." />
      <div className="max-w-4xl space-y-6">
        <ErrorNote error={Object.keys(errors).length ? null : error} />
        <Card>
          <CardHeader title="Video intercom (LiveKit)" action={data.livekit_configured ? <Badge tone="green">Configured</Badge> : <Badge tone="amber">Not configured</Badge>} />
          <div className="space-y-4 p-5 sm:p-6">
            <FormFields fields={livekitFields} values={values} errors={errors} record={record} onChange={change} />
            <SourceNote sources={data.sources} names={["livekit_url", "livekit_api_key", "livekit_api_secret"]} />
            <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
              <Button busy={busy === "livekit"} onClick={() => save("livekit")}>Save &amp; test connection</Button>
            </div>
          </div>
        </Card>
        <Card>
          <CardHeader title="Push notifications (Firebase)" action={data.fcm_configured ? <Badge tone="green">Configured</Badge> : <Badge tone="amber">Not configured</Badge>} />
          <div className="space-y-4 p-5 sm:p-6">
            <p className="text-sm text-muted">Without Firebase, residents are only rung while the app is open.</p>
            <FormFields fields={fcmFields} values={values} errors={errors} record={record} onChange={change} />
            <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
              <Button busy={busy === "fcm"} onClick={() => save("fcm")}>Save &amp; test Firebase</Button>
            </div>
          </div>
        </Card>
        <Card>
          <CardHeader title="Gate relays & LPR tuning" />
          <div className="p-5 sm:p-6"><FormFields fields={tuningFields} values={values} errors={errors} record={record} onChange={change} /></div>
        </Card>
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted">{data.updated_at && `Last saved ${formatDateTime(data.updated_at)}`}</span>
          <Button variant="primary" busy={busy === "save"} onClick={() => save()}>Save all settings</Button>
        </div>
      </div>
    </>
  );
}
