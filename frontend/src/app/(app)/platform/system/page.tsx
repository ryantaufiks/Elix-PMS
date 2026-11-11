"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";

import { type FieldDef, FormFields, initialValues } from "@/components/forms";
import { Icon, type IconName } from "@/components/icons";
import { Badge, Button, Card, Empty, ErrorNote, Input, Loading, Modal, PageHeader, Pagination, Select, Table, Td, Th, useToast } from "@/components/ui";
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
  { name: "ai_usd_per_million_input", label: "Cost per 1M input tokens (USD)", type: "number", nullable: true, hint: "Your OpenAI price for the chat model, for the usage report's cost estimate. Blank: no estimate." },
  { name: "ai_usd_per_million_output", label: "Cost per 1M output tokens (USD)", type: "number", nullable: true },
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

type Section = {
  key: "livekit" | "fcm" | "email" | "assistant" | "tuning";
  title: string;
  icon: IconName;
  what: string;
  fields: FieldDef[];
  ready: (s: SystemSettings) => boolean | null;  // null: optional, shown as defaults/custom
  test?: string;
  envNames?: string[];
};

const SECTIONS: Section[] = [
  { key: "livekit", title: "Video intercom", icon: "video", what: "Video calls between the lobby kiosk and residents' phones (LiveKit Cloud).",
    fields: livekitFields, ready: (s) => s.livekit_configured, test: "Save & test connection", envNames: ["livekit_url", "livekit_api_key", "livekit_api_secret"] },
  { key: "fcm", title: "Push notifications", icon: "bell", what: "Lets residents' phones ring for visitors even when the app is closed (Firebase).",
    fields: fcmFields, ready: (s) => s.fcm_configured, test: "Save & test Firebase" },
  { key: "email", title: "Email", icon: "mail", what: "Sends subscription reminders, usage warnings and alerts from your mail server (SMTP).",
    fields: emailFields, ready: (s) => s.email_configured, test: "Save & send test email", envNames: ["smtp_host", "smtp_password", "email_from_address"] },
  { key: "assistant", title: "Kiosk AI assistant", icon: "sparkle", what: "The voice assistant visitors talk to on the kiosk (OpenAI). Each site turns it on under Site setup.",
    fields: assistantFields, ready: (s) => s.openai_configured, envNames: ["openai_api_key"] },
  { key: "tuning", title: "Gates & plate cameras", icon: "cpu", what: "How long to wait for a relay, and how long to ignore the same plate read twice.",
    fields: tuningFields, ready: () => null },
];

function SourceNote({ sources, names }: { sources: SystemSettings["sources"]; names: string[] }) {
  const fromEnv = names.filter((n) => sources[n] === ".env");
  if (!fromEnv.length) return null;
  return <p className="text-xs text-muted">Blank fields fall back to the server&apos;s .env file. Currently from .env: {fromEnv.join(", ")}.</p>;
}

const EMAIL_STATUS = { queued: "amber", sent: "green", failed: "red" } as const;

function EmailLogList() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const { data } = useSWR<Page<EmailLog>>(`/v1/email-logs/${query({ page, status })}`, { keepPreviousData: true, refreshInterval: 15000 });
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted">Every email of the last 30 days.</p>
        <Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className="w-36" aria-label="Status">
          <option value="">All</option><option value="sent">Sent</option><option value="failed">Failed</option><option value="queued">Queued</option>
        </Select>
      </div>
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
    </div>
  );
}

export default function SystemSettingsPage() {
  const { me } = useSession();
  const toast = useToast();
  const { data, mutate } = useSWR<SystemSettings>(me.is_superuser ? "/v1/system-settings/" : null);
  const [open, setOpen] = useState<Section | null>(null);
  const [log, setLog] = useState(false);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [testTo, setTestTo] = useState("");
  useEffect(() => {
    if (data && open) setValues(initialValues(open.fields, data as unknown as Record<string, unknown>));
  }, [data, open]);

  if (!me.is_superuser) return <Card><Empty>Only the platform administrator can change system settings.</Empty></Card>;
  if (!data) return <Loading />;

  const errors = error instanceof ApiError && error.data && typeof error.data === "object"
    ? Object.fromEntries(Object.entries(error.data as Record<string, unknown>).filter(([k]) => k !== "detail").map(([k, v]) => [k, errorMessage(v, "Invalid")]))
    : {};
  const required = SECTIONS.filter((x) => x.ready(data) !== null);
  const done = required.filter((x) => x.ready(data)).length;

  function edit(section: Section) {
    setError(null);
    setOpen(section);
  }

  async function save(section: Section, test: boolean) {
    setBusy(test ? "test" : "save");
    setError(null);
    try {
      const body: Record<string, unknown> = {};
      for (const f of section.fields) {
        const v = values[f.name];
        if ((f.type === "secret" || f.type === "secret-text") && v === "") continue;
        if (f.required && (v === "" || v === null)) continue;  // Keep the saved value rather than clear a required one.
        body[f.name] = f.type === "number" ? (v === "" || v === null ? null : Number(v)) : v;
      }
      await api("/v1/system-settings/", { method: "PATCH", body });
      await mutate();
      if (test && section.test) {
        const result = await api<{ ok: boolean; detail: string }>(`/v1/system-settings/test-${section.key}/`,
          { method: "POST", body: section.key === "email" ? { to: testTo.trim() || undefined } : undefined });
        toast(result.ok ? "success" : "error", result.detail);
        if (!result.ok) return;
      } else {
        toast("success", `${section.title} saved. It applies immediately.`);
      }
      setOpen(null);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <PageHeader title="System settings" description="Services every condominium uses. Open a card to set it up; secrets are stored encrypted and never shown again." />
      <div className={`mb-6 flex items-center gap-3 rounded-xl border px-4 py-3 text-sm ${done === required.length ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-900 dark:text-emerald-200" : "border-amber-500/40 bg-amber-500/10 text-amber-900 dark:text-amber-200"}`}>
        <Icon name={done === required.length ? "check" : "bell"} className="h-5 w-5 shrink-0" />
        <span><strong>{done} of {required.length}</strong> services set up{data.updated_at && ` · last change ${formatDateTime(data.updated_at)}`}</span>
      </div>
      <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {SECTIONS.map((section) => {
          const ready = section.ready(data);
          return (
            <Card key={section.key} className="flex flex-col">
              <div className="flex flex-1 flex-col p-5 sm:p-6">
                <div className="flex items-start justify-between gap-3">
                  <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary-500/10 text-primary-600 dark:text-primary-300"><Icon name={section.icon} className="h-6 w-6" /></span>
                  {ready === null ? <Badge>Optional</Badge> : ready ? <Badge tone="green">Set up</Badge> : <Badge tone="amber">Not set up</Badge>}
                </div>
                <h2 className="mt-4 text-lg font-semibold text-ink">{section.title}</h2>
                <p className="mt-1 flex-1 text-sm text-body">{section.what}</p>
                <div className="mt-5 flex flex-wrap gap-2">
                  <Button variant={ready === false ? "primary" : "secondary"} onClick={() => edit(section)}>{ready === false ? "Set up" : "Change"}</Button>
                  {section.key === "email" && <Button variant="ghost" onClick={() => setLog(true)}>Email log</Button>}
                </div>
              </div>
            </Card>
          );
        })}
      </div>

      <Modal wide open={!!open} onClose={() => setOpen(null)} title={open?.title ?? ""}
        footer={open && (
          <>
            <Button onClick={() => setOpen(null)}>Cancel</Button>
            {open.test && <Button busy={busy === "test"} onClick={() => save(open, true)}>{open.test}</Button>}
            <Button variant="primary" busy={busy === "save"} onClick={() => save(open, false)}>Save</Button>
          </>
        )}>
        {open && (
          <div className="space-y-4">
            <p className="text-sm text-body">{open.what}</p>
            <ErrorNote error={Object.keys(errors).length ? null : error} />
            <FormFields fields={open.fields} values={values} errors={errors} record={data as unknown as Record<string, unknown>}
              onChange={(n, v) => setValues((s) => ({ ...s, [n]: v }))} />
            {open.envNames && <SourceNote sources={data.sources} names={open.envNames} />}
            {open.key === "email" && (
              <div className="border-t border-line pt-4">
                <label className="text-sm font-medium text-ink" htmlFor="test-to">Send the test email to</label>
                <Input id="test-to" type="email" value={testTo} onChange={(e) => setTestTo(e.target.value)} placeholder={me.email || "you@company.com"} className="mt-1" />
              </div>
            )}
          </div>
        )}
      </Modal>
      <Modal wide open={log} onClose={() => setLog(false)} title="Email log">
        {log && <EmailLogList />}
      </Modal>
    </>
  );
}
