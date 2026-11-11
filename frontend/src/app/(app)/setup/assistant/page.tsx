"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";

import { AuthImage } from "@/components/bits";
import { ConfirmDialog, EntityModal, type FieldDef, FormFields, initialValues, remove } from "@/components/forms";
import { Icon, type IconName } from "@/components/icons";
import { Badge, Button, Card, CardHeader, Checkbox, Empty, ErrorNote, Field, Input, Loading, Modal, PageHeader, Textarea, type Tone, useToast } from "@/components/ui";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { AssistantAction, AssistantMap, AssistantModule, AssistantSettings, Page } from "@/lib/types";
import { ModuleGate } from "@/components/ModuleGate";

const settingsFields: FieldDef[] = [
  { name: "enabled", label: "Show the assistant on this site's kiosks", type: "checkbox", wide: true },
  { name: "name", label: "Name", required: true, placeholder: "e.g. Ava" },
  { name: "languages", label: "Languages", hint: "It answers in the visitor's language." },
  { name: "greeting", label: "Greeting", wide: true, hint: "Spoken when a visitor starts a conversation." },
  { name: "instructions", label: "Extra guidance", type: "textarea", wide: true, placeholder: "e.g. Mention that visitor parking is free for the first 2 hours." },
  { name: "openai_api_key", label: "This site's own OpenAI key (optional)", type: "secret", wide: true, hint: "Blank uses the platform key. Set one to bill this site's usage to its own OpenAI account." },
];

const moduleFields: FieldDef[] = [
  { name: "title", label: "Title", required: true, wide: true },
  { name: "content", label: "What the assistant should know", type: "textarea", required: true, wide: true,
    hint: "Plain sentences work best: where things are, opening hours, rules, who to contact." },
  { name: "order", label: "Order", type: "number" },
  { name: "is_active", label: "In use", type: "checkbox" },
];

const VIEWS = ["knowledge", "maps", "try"] as const;
type View = (typeof VIEWS)[number];

const STARTERS = ["Directions & blocks", "Facilities & opening hours", "Visitor rules & parking", "Deliveries & parcels", "Contacts & guardhouse", "Getting here: MRT, bus, taxi"];

const ACTION_LABEL = (a: AssistantAction, maps: AssistantMap[]) => {
  switch (a.type) {
    case "show_map": return `Shows map: ${maps.find((m) => m.id === a.map_id)?.name ?? a.map_id}`;
    case "start_walk_in": return `Opens walk-in for ${a.unit}${a.visitor_name ? `, ${a.visitor_name}` : ""}${a.purpose ? ` (${a.purpose})` : ""}`;
    case "call_resident": return `Opens call to ${a.unit}`;
    case "open_screen": return a.screen === "invitation" ? "Opens invitation QR scan" : "Opens check-out";
    case "end_conversation": return "Ends the conversation";
  }
};

function AssistantSetupPage() {
  const { condo, isAdmin } = useSession();
  const toast = useToast();
  const base = `?condominium=${condo.id}`;
  const { data: settings, mutate: reloadSettings } = useSWR<AssistantSettings>(isAdmin ? `/v1/assistant-settings/${base}` : null);
  const { data: modules, mutate: reloadModules } = useSWR<Page<AssistantModule>>(isAdmin ? `/v1/assistant-modules/${base}&page_size=100` : null);
  const { data: maps, mutate: reloadMaps } = useSWR<Page<AssistantMap>>(isAdmin ? `/v1/assistant-maps/${base}&page_size=100` : null);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [error, setError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const [module, setModule] = useState<AssistantModule | { title: string } | null>(null);
  const [map, setMap] = useState<AssistantMap | "new" | null>(null);
  const [removing, setRemoving] = useState<{ kind: "module" | "map"; id: number; name: string } | null>(null);
  const [editingSettings, setEditingSettings] = useState(false);
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

  useEffect(() => {
    if (settings) setValues(initialValues(settingsFields, settings as unknown as Record<string, unknown>));
  }, [settings]);

  if (!isAdmin) return <Card><Empty>Only the site admin sets up the assistant.</Empty></Card>;
  if (!settings) return <Loading />;

  const errors = error instanceof ApiError && error.data && typeof error.data === "object"
    ? Object.fromEntries(Object.entries(error.data as Record<string, unknown>).filter(([k]) => k !== "detail").map(([k, v]) => [k, errorMessage(v, "Invalid")]))
    : {};

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const body = { ...values };
      if (body.openai_api_key === "") delete body.openai_api_key;
      await api(`/v1/assistant-settings/${base}`, { method: "PATCH", body });
      await reloadSettings();
      setEditingSettings(false);
      toast("success", "Assistant saved. Kiosks pick it up on their next conversation.");
    } catch (err) {
      setError(err);
    } finally {
      setSaving(false);
    }
  }

  const mapList = maps?.results ?? [];

  const moduleList = modules?.results ?? [];
  const activeTopics = moduleList.filter((x) => x.is_active).length;
  const CARDS: { key: View | "settings"; title: string; icon: IconName; what: string; badge: { tone: Tone; label: string }; primary?: boolean }[] = [
    { key: "settings", title: "Assistant", icon: "sparkle", what: "Its name, greeting and languages, any extra guidance, and whether kiosks show it.",
      badge: settings.enabled ? { tone: "green", label: "On at kiosks" } : { tone: "slate", label: "Off" } },
    { key: "knowledge", title: "Knowledge", icon: "report", what: "What the assistant knows about this site: directions, facilities, rules, contacts.",
      badge: activeTopics ? { tone: "green", label: `${activeTopics} topic${activeTopics === 1 ? "" : "s"}` } : { tone: "amber", label: "Start here" }, primary: !activeTopics },
    { key: "maps", title: "Maps & floor plans", icon: "grid", what: "Pictures the assistant can put on the kiosk screen when it gives directions.",
      badge: mapList.length ? { tone: "green", label: `${mapList.length} map${mapList.length === 1 ? "" : "s"}` } : { tone: "slate", label: "Optional" } },
    { key: "try", title: "Try it", icon: "mic", what: "Type a question as a visitor would, and see what the assistant answers and does.",
      badge: { tone: "blue", label: "Test" } },
  ];
  const current = CARDS.find((c) => c.key === view);

  return (
    <>
      {!current ? (
        <>
          <PageHeader title="AI Assistant" description="A voice concierge on the kiosk: directions, facilities, rules, and help registering a visit. It only talks about this site, never reveals residents, and stores nothing visitors say." />
          <div className={`mb-6 flex items-center gap-3 rounded-xl border px-4 py-3 text-sm ${settings.enabled ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-900 dark:text-emerald-200" : "border-line bg-surface text-body"}`}>
            <Icon name={settings.enabled ? "check" : "bell"} className="h-5 w-5 shrink-0" />
            <span>
              {settings.enabled ? <><strong>{settings.name || "The assistant"}</strong> is on at this site&apos;s kiosks</> : <><strong>The assistant is off.</strong> Turn it on under Assistant when it knows enough</>}
              {" · "}{activeTopics} knowledge topic{activeTopics === 1 ? "" : "s"} · {mapList.length} map{mapList.length === 1 ? "" : "s"}
            </span>
          </div>
          <div className="grid gap-5 md:grid-cols-2">
            {CARDS.map((c) => (
              <Card key={c.key} className="flex flex-col">
                <div className="flex flex-1 flex-col p-5 sm:p-6">
                  <div className="flex items-start justify-between gap-3">
                    <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary-500/10 text-primary-600 dark:text-primary-300"><Icon name={c.icon} className="h-6 w-6" /></span>
                    <Badge tone={c.badge.tone}>{c.badge.label}</Badge>
                  </div>
                  <h2 className="mt-4 text-lg font-semibold text-ink">{c.title}</h2>
                  <p className="mt-1 flex-1 text-sm text-body">{c.what}</p>
                  <div className="mt-5">
                    <Button variant={c.primary ? "primary" : "secondary"} onClick={() => (c.key === "settings" ? setEditingSettings(true) : setView(c.key))}>
                      {c.key === "settings" ? "Change" : c.key === "try" ? "Try it" : "Open"}
                    </Button>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </>
      ) : (
        <>
          <button onClick={() => setView(null)} className="mb-4 inline-flex items-center gap-1.5 text-sm font-medium text-primary-600 hover:underline dark:text-primary-400">
            <Icon name="chevron" className="h-4 w-4 rotate-180" /> All assistant settings
          </button>
          <PageHeader title={current.title} description={current.what}
            action={view === "knowledge" ? <Button variant="primary" onClick={() => setModule({ title: "" })}><Icon name="plus" className="h-4 w-4" /> Add topic</Button>
              : view === "maps" ? <Button variant="primary" onClick={() => setMap("new")}><Icon name="plus" className="h-4 w-4" /> Add map</Button> : undefined} />
          <div>
            {view === "knowledge" && (
              <Card>
                {!modules ? <Loading /> : moduleList.length === 0 ? (
                  <div className="space-y-3 p-5 text-sm text-muted sm:p-6">
                    <p>Add what the assistant should know. Start with one of these:</p>
                    <div className="flex flex-wrap gap-2">
                      {STARTERS.map((t) => <Button key={t} size="sm" onClick={() => setModule({ title: t })}>{t}</Button>)}
                    </div>
                  </div>
                ) : (
                  <ul className="divide-y divide-line">
                    {moduleList.map((x) => (
                      <li key={x.id} className="px-5 py-4 sm:px-6">
                        <div className="flex flex-wrap items-center gap-2 font-medium text-ink">{x.title}{x.is_active ? <Badge tone="green">In use</Badge> : <Badge>Not in use</Badge>}</div>
                        <p className="mt-1 line-clamp-2 text-sm text-muted">{x.content}</p>
                        <div className="-ml-2 mt-2 flex gap-1">
                          <Button size="sm" onClick={() => setModule(x)}>Edit</Button>
                          <Button size="sm" variant="ghost" onClick={() => setRemoving({ kind: "module", id: x.id, name: x.title })}>Delete</Button>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            )}
            {view === "maps" && (
              <Card>
                {!maps ? <Loading /> : mapList.length === 0 ? <Empty>The assistant can put a map on the kiosk screen when it gives directions. Upload a site map or floor plans.</Empty> : (
                  <div className="grid gap-4 p-5 sm:grid-cols-2 lg:grid-cols-3">
                    {mapList.map((x) => (
                      <div key={x.id} className="overflow-hidden rounded-lg border border-line">
                        <AuthImage path={`/v1/assistant-maps/${x.id}/image/`} alt={x.name} className="h-40 w-full bg-surface-2 object-contain" />
                        <div className="p-3">
                          <div className="flex flex-wrap items-center gap-2 text-sm font-medium text-ink">{x.name}{!x.is_active && <Badge>Not in use</Badge>}</div>
                          {x.description && <p className="mt-0.5 line-clamp-2 text-xs text-muted">{x.description}</p>}
                          <div className="-ml-2 mt-2 flex gap-1">
                            <Button size="sm" onClick={() => setMap(x)}>Edit</Button>
                            <Button size="sm" variant="ghost" onClick={() => setRemoving({ kind: "map", id: x.id, name: x.name })}>Delete</Button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            )}
            {view === "try" && <TryIt condoId={condo.id} maps={mapList} />}
          </div>
        </>
      )}

      <Modal wide open={editingSettings} onClose={() => setEditingSettings(false)} title="Assistant"
        footer={<><Button onClick={() => setEditingSettings(false)}>Cancel</Button><Button variant="primary" busy={saving} onClick={save}>Save</Button></>}>
        <div className="space-y-4">
          <ErrorNote error={Object.keys(errors).length ? null : error} />
          <FormFields fields={settingsFields} values={values} errors={errors} record={settings as unknown as Record<string, unknown>} onChange={(n, v) => setValues((st) => ({ ...st, [n]: v }))} />
        </div>
      </Modal>
      {module && (
        <EntityModal wide title={"id" in module ? `Edit ${module.title}` : "Add knowledge"} fields={moduleFields}
          record={"id" in module ? (module as unknown as Record<string, unknown>) : null}
          defaults={{ title: module.title, order: (modules?.count ?? 0) + 1, is_active: true }}
          endpoint={"id" in module ? `/v1/assistant-modules/${module.id}/` : "/v1/assistant-modules/"} extra={{ condominium: condo.id }}
          onClose={() => setModule(null)} onSaved={() => { setModule(null); reloadModules(); }} />
      )}
      {map && <MapModal condoId={condo.id} map={map === "new" ? null : map} onClose={() => setMap(null)} onSaved={() => { setMap(null); reloadMaps(); }} />}
      <ConfirmDialog open={!!removing} title="Delete?" confirmLabel="Delete" onClose={() => setRemoving(null)}
        message={<>Delete <strong>{removing?.name}</strong>? The assistant stops using it straight away.</>}
        onConfirm={async () => {
          await remove(`/v1/assistant-${removing!.kind === "map" ? "maps" : "modules"}/${removing!.id}/`);
          if (removing!.kind === "map") reloadMaps(); else reloadModules();
        }} />
    </>
  );
}

function MapModal({ condoId, map, onClose, onSaved }: { condoId: number; map: AssistantMap | null; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(map?.name ?? "");
  const [description, setDescription] = useState(map?.description ?? "");
  const [active, setActive] = useState(map?.is_active ?? true);
  const [image, setImage] = useState<File | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = new FormData();
    body.set("condominium", String(condoId));
    body.set("name", name);
    body.set("description", description);
    body.set("is_active", String(active));
    if (image) body.set("image", image);
    try {
      await api(map ? `/v1/assistant-maps/${map.id}/` : "/v1/assistant-maps/", { method: map ? "PATCH" : "POST", body });
      onSaved();
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} title={map ? `Edit ${map.name}` : "Add map"}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" type="submit" form="map-form" busy={busy}>Save</Button></>}>
      <form id="map-form" onSubmit={save} className="space-y-4">
        <ErrorNote error={error} />
        <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} required placeholder="e.g. Site map, or Tower B level 1" /></Field>
        <Field label="What it shows" hint="Areas and landmarks on it, so the assistant knows when to show it.">
          <Textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="e.g. All towers, the pool, gym, visitor car park and drop-off point" />
        </Field>
        <Field label={map ? "Replace image (optional)" : "Image"} hint="PNG or JPG. A clear, high-contrast plan reads best on the kiosk.">
          <Input type="file" accept="image/png,image/jpeg,image/webp" required={!map} onChange={(e) => setImage(e.target.files?.[0] ?? null)} />
        </Field>
        <Checkbox label="In use" checked={active} onChange={(e) => setActive(e.target.checked)} />
      </form>
    </Modal>
  );
}

/** A typed conversation with the saved knowledge, to check the answers before visitors hear them. */
function TryIt({ condoId, maps }: { condoId: number; maps: AssistantMap[] }) {
  const [history, setHistory] = useState<{ role: "user" | "assistant"; content: string; actions?: AssistantAction[] }[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const text = message.trim();
    if (!text) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ reply: string; actions: AssistantAction[] }>(`/v1/assistant-settings/test/?condominium=${condoId}`, {
        method: "POST", body: { message: text, history: history.map(({ role, content }) => ({ role, content })) },
      });
      setHistory((h) => [...h, { role: "user", content: text }, { role: "assistant", content: r.reply, actions: r.actions }]);
      setMessage("");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader title="Try it" action={history.length > 0 && <Button size="sm" variant="ghost" onClick={() => setHistory([])}>Clear</Button>} />
      <div className="space-y-3 p-5">
        <p className="text-sm text-muted">Type what a visitor might ask. Uses the saved settings (save first), in text only.</p>
        {history.map((h, i) => (
          <div key={i} className={h.role === "user" ? "flex justify-end" : ""}>
            <div className={h.role === "user" ? "max-w-[80%] rounded-2xl rounded-br-sm bg-primary-600 px-4 py-2 text-sm text-white" : "max-w-[80%] rounded-2xl rounded-bl-sm bg-surface-2 px-4 py-2 text-sm text-ink"}>
              {h.content || <span className="italic text-muted">(no words, only an action)</span>}
              {h.actions?.map((a, j) => <div key={j} className="mt-1"><Badge tone="blue">{ACTION_LABEL(a, maps)}</Badge></div>)}
            </div>
          </div>
        ))}
        <ErrorNote error={error} />
        <form onSubmit={send} className="flex gap-2">
          <Input value={message} onChange={(e) => setMessage(e.target.value)} placeholder="e.g. Where is the swimming pool?" maxLength={1000} />
          <Button variant="primary" type="submit" busy={busy}><Icon name="send" className="h-4 w-4" /> Send</Button>
        </form>
      </div>
    </Card>
  );
}

export default function Page() {
  return <ModuleGate module="ai_concierge"><AssistantSetupPage /></ModuleGate>;
}
