"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";

import { type FieldDef, FormFields, initialValues } from "@/components/forms";
import { Badge, Button, Card, CardHeader, Empty, ErrorNote, Input, Loading, PageHeader, Pagination, Select, Table, Td, Th, useToast } from "@/components/ui";
import { api, ApiError, errorMessage, query } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useSession } from "@/lib/session";
import type { EmailLog, Page, SystemSettings } from "@/lib/types";

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
const VOICES = ["alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse", "marin", "cedar"].map((v) => ({ value: v, label: v[0].toUpperCase() + v.slice(1) }));
const assistantFields: FieldDef[] = [
  { name: "openai_api_key", label: "OpenAI API key", type: "secret", wide: true, hint: "platform.openai.com > API keys. Used by every site unless the site sets its own key." },
  { name: "assistant_mode", label: "Mode", type: "select", wide: true, options: [
    { value: "pipeline", label: "Speech to text: transcribe, answer, speak (lower cost, short pause per answer)" },
    { value: "realtime", label: "Realtime voice: live two-way conversation (most natural, higher cost)" },
  ] },
  { name: "assistant_voice", label: "Voice", type: "select", options: VOICES },
  { name: "assistant_chat_model", label: "Chat model", hint: "Speech-to-text mode. Default gpt-4.1-mini." },
  { name: "assistant_transcribe_model", label: "Transcription model", hint: "Default gpt-4o-mini-transcribe." },
  { name: "assistant_tts_model", label: "Text-to-speech model", hint: "Speech-to-text mode. Default gpt-4o-mini-tts." },
  { name: "assistant_realtime_model", label: "Realtime model", hint: "Realtime mode. Default gpt-realtime-mini." },
  { name: "assistant_max_session_seconds", label: "Longest conversation (seconds)", type: "number", required: true, hint: "Default 180." },
  { name: "assistant_daily_sessions", label: "Conversations per kiosk per day", type: "number", required: true, hint: "Caps each kiosk's OpenAI bill. Default 100." },
];
const emailFields: FieldDef[] = [
  { name: "smtp_host", label: "SMTP host", placeholder: "smtp.office365.com" },
  { name: "smtp_port", label: "Port", type: "number", hint: "Default 587." },
  { name: "smtp_security", label: "Security", type: "select", options: [
    { value: "", label: "Default (STARTTLS)" },
    { value: "starttls", label: "STARTTLS (usually port 587)" },
    { value: "ssl", label: "SSL/TLS (usually port 465)" },
    { value: "none", label: "None (port 25, trusted networks only)" },
  ] },
  { name: "smtp_username", label: "Username", hint: "Often the full mailbox address." },
  { name: "smtp_password", label: "Password", type: "secret", hint: "For Microsoft 365 or Gmail with two-step sign-in, use an app password." },
  { name: "email_from_address", label: "From address", type: "email", placeholder: "no-reply@yourcompany.com.sg" },
  { name: "email_from_name", label: "From name", placeholder: "Elix", hint: "Default Elix." },
  { name: "email_reply_to", label: "Reply-to address", type: "email", hint: "Where replies go, e.g. your support mailbox." },
];
const ALL = [...livekitFields, ...fcmFields, ...assistantFields, ...emailFields, ...tuningFields];
const EMAIL_STATUS = { queued: "amber", sent: "green", failed: "red" } as const;

function EmailLogCard() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const { data } = useSWR<Page<EmailLog>>(`/v1/email-logs/${query({ page, status })}`, { keepPreviousData: true, refreshInterval: 15000 });
  return (
    <Card>
      <CardHeader title="Email log" action={
        <Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className="w-36">
          <option value="">All</option><option value="sent">Sent</option><option value="failed">Failed</option><option value="queued">Queued</option>
        </Select>
      } />
      {!data ? <Loading /> : data.results.length === 0 ? <Empty>No emails in the last 30 days.</Empty> : (
        <>
          <Table>
            <thead><tr><Th>When</Th><Th>To</Th><Th>Subject</Th><Th>Status</Th></tr></thead>
            <tbody className="divide-y divide-line">
              {data.results.map((e) => (
                <tr key={e.id}>
                  <Td className="whitespace-nowrap">{formatDateTime(e.created_at)}</Td>
                  <Td>{e.to}{e.condominium_name && <div className="text-xs text-muted">{e.condominium_name}</div>}</Td>
                  <Td>{e.subject}{e.error && <div className="text-xs text-rose-600">{e.error}</div>}</Td>
                  <Td><Badge tone={EMAIL_STATUS[e.status]}>{e.status[0].toUpperCase() + e.status.slice(1)}</Badge></Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <Pagination page={page} count={data.count} onPage={setPage} />
        </>
      )}
    </Card>
  );
}

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
  const [testTo, setTestTo] = useState("");
  useEffect(() => {
    if (data) setValues(initialValues(ALL, data as unknown as Record<string, unknown>));
  }, [data]);

  if (!me.is_superuser) return <Card><Empty>Only the platform administrator can change system settings.</Empty></Card>;
  if (!data) return <Loading />;

  const errors = error instanceof ApiError && error.data && typeof error.data === "object"
    ? Object.fromEntries(Object.entries(error.data as Record<string, unknown>).filter(([k]) => k !== "detail").map(([k, v]) => [k, errorMessage(v, "Invalid")]))
    : {};

  async function save(then?: "livekit" | "fcm" | "email") {
    setBusy(then ?? "save");
    setError(null);
    try {
      const body: Record<string, unknown> = {};
      for (const f of ALL) {
        const v = values[f.name];
        if ((f.type === "secret" || f.type === "secret-text") && v === "") continue;
        if (f.required && (v === "" || v === null)) continue;  // Keep the saved value rather than clear a required one.
        body[f.name] = f.type === "number" ? (v === "" || v === null ? null : Number(v)) : v;
      }
      await api("/v1/system-settings/", { method: "PATCH", body });
      await mutate();
      if (then) {
        const result = await api<{ ok: boolean; detail: string }>(`/v1/system-settings/test-${then}/`,
          { method: "POST", body: then === "email" ? { to: testTo.trim() || undefined } : undefined });
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
            <div className="flex justify-end gap-2 border-t border-line pt-4">
              <Button busy={busy === "livekit"} onClick={() => save("livekit")}>Save &amp; test connection</Button>
            </div>
          </div>
        </Card>
        <Card>
          <CardHeader title="Push notifications (Firebase)" action={data.fcm_configured ? <Badge tone="green">Configured</Badge> : <Badge tone="amber">Not configured</Badge>} />
          <div className="space-y-4 p-5 sm:p-6">
            <p className="text-sm text-muted">Without Firebase, residents are only rung while the app is open.</p>
            <FormFields fields={fcmFields} values={values} errors={errors} record={record} onChange={change} />
            <div className="flex justify-end gap-2 border-t border-line pt-4">
              <Button busy={busy === "fcm"} onClick={() => save("fcm")}>Save &amp; test Firebase</Button>
            </div>
          </div>
        </Card>
        <Card>
          <CardHeader title="Kiosk AI assistant (OpenAI)" action={data.openai_configured ? <Badge tone="green">Configured</Badge> : <Badge tone="amber">Not configured</Badge>} />
          <div className="space-y-4 p-5 sm:p-6">
            <p className="text-sm text-muted">Visitors talk to the assistant on the kiosk. Each site turns it on and writes what it knows under Site setup → AI Assistant. Nothing visitors say is stored.</p>
            <FormFields fields={assistantFields} values={values} errors={errors} record={record} onChange={change} />
            <SourceNote sources={data.sources} names={["openai_api_key"]} />
          </div>
        </Card>
        <Card>
          <CardHeader title="Email (SMTP)" action={data.email_configured ? <Badge tone="green">Configured</Badge> : <Badge tone="amber">Not configured</Badge>} />
          <div className="space-y-4 p-5 sm:p-6">
            <p className="text-sm text-muted">Outgoing email for subscription notices and alerts. Every message is listed in the email log below for 30 days.</p>
            <FormFields fields={emailFields} values={values} errors={errors} record={record} onChange={change} />
            <SourceNote sources={data.sources} names={["smtp_host", "smtp_password", "email_from_address"]} />
            <div className="flex flex-col gap-2 border-t border-line pt-4 sm:flex-row sm:items-center sm:justify-end">
              <Input type="email" value={testTo} onChange={(e) => setTestTo(e.target.value)} placeholder={me.email || "Send the test to…"} className="sm:w-64" aria-label="Send the test email to" />
              <Button busy={busy === "email"} onClick={() => save("email")}>Save &amp; send test email</Button>
            </div>
          </div>
        </Card>
        <EmailLogCard />
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
