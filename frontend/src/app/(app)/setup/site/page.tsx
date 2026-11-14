"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";

import { type FieldDef, FormFields, initialValues } from "@/components/forms";
import { Icon } from "@/components/icons";
import { PlanSummary, STATUS, statusDate } from "@/components/PlanSummary";
import { Badge, Button, Card, CardHeader, cx, Empty, ErrorNote, PageHeader, useToast } from "@/components/ui";
import { api, ApiError, errorMessage } from "@/lib/api";
import { condoFields } from "@/lib/fields";
import { useSession } from "@/lib/session";
import type { Condominium, Subscription } from "@/lib/types";

/** The form split into one card per section (the fields before the first section are the condominium itself). */
function groups(fields: FieldDef[]): { title: string; fields: FieldDef[] }[] {
  const out: { title: string; fields: FieldDef[] }[] = [];
  for (const f of fields) {
    if (f.section || out.length === 0) out.push({ title: f.section ?? "Condominium", fields: [] });
    out[out.length - 1].fields.push({ ...f, section: undefined });
  }
  return out;
}

/** One line on the site's plan, opening the full summary on request. */
function PlanStrip({ condoId }: { condoId: number }) {
  const { data } = useSWR<Subscription>(`/v1/subscriptions/${condoId}/`);
  const [open, setOpen] = useState(false);
  if (!data) return null;
  const status = STATUS[data.status];
  return (
    <div className="mb-6 max-w-4xl">
      <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-line bg-surface px-5 py-3 shadow-card">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-500/10 text-primary-500 dark:text-primary-300"><Icon name="tag" className="h-5 w-5" /></span>
        <div className="min-w-0 flex-1 text-sm">
          <span className="font-semibold text-ink">Your plan: {data.plan_name}</span>
          <span className="ml-2"><Badge tone={status.tone}>{status.label} {statusDate(data)}</Badge></span>
        </div>
        <Button size="sm" variant="ghost" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          {open ? "Hide details" : "Plan details"}
          <Icon name="chevron" className={cx("h-4 w-4 transition-transform", open ? "-rotate-90" : "rotate-90")} />
        </Button>
      </div>
      {open && <div className="mt-3"><PlanSummary condoId={condoId} /></div>}
    </div>
  );
}

export default function SiteSettingsPage() {
  const { condo, isAdmin, me, reload } = useSession();
  const toast = useToast();
  const fields = condoFields({ superuser: me.is_superuser, creating: false, modules: condo.modules });
  const sections = useMemo(() => groups(fields), [me.is_superuser]); // eslint-disable-line react-hooks/exhaustive-deps
  const [values, setValues] = useState(() => initialValues(fields, condo));
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => setValues(initialValues(fields, condo)), [condo.id]);
  const saved = JSON.stringify(initialValues(fields, condo));
  const dirty = JSON.stringify(values) !== saved;

  // Leaving with unsaved changes asks first.
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  if (!isAdmin) return <Card><Empty>Site settings are managed by the site admin.</Empty></Card>;

  const errors = error instanceof ApiError && error.data && typeof error.data === "object"
    ? Object.fromEntries(Object.entries(error.data as Record<string, unknown>).filter(([k]) => k !== "detail").map(([k, v]) => [k, errorMessage(v, "Invalid")]))
    : {};

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api<Condominium>(`/v1/condominiums/${condo.id}/`, { method: "PATCH", body: values });
      await reload();
      toast("success", "Site settings saved.");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Site settings" description={`Details and visitor policy for ${condo.name}.`} />
      <PlanStrip condoId={condo.id} />
      <form onSubmit={save} className="max-w-4xl space-y-6">
        <ErrorNote error={Object.keys(errors).length ? null : error} />
        {sections.map((s) => (
          <Card key={s.title}>
            <CardHeader title={s.title} />
            <div className="p-5 sm:p-6">
              <FormFields fields={s.fields} values={values} errors={errors} record={condo} onChange={(n, v) => setValues((st) => ({ ...st, [n]: v }))} />
            </div>
          </Card>
        ))}
        {/* Always in reach: sticks to the bottom of the window while the form scrolls. */}
        <div className={cx("sticky bottom-4 z-10 flex items-center gap-3 rounded-2xl border px-4 py-3 shadow-lg backdrop-blur",
          dirty ? "border-amber-400/50 bg-surface/95" : "border-line bg-surface/95")}>
          <span className="flex-1 text-sm">
            {dirty ? <><span className="mr-2 inline-block h-2 w-2 rounded-full bg-amber-500" /><span className="text-ink"><span className="hidden sm:inline">Unsaved changes</span><span className="sm:hidden">Unsaved</span></span></>
                   : <span className="text-muted">All changes saved</span>}
          </span>
          {dirty && <Button type="button" variant="ghost" onClick={() => { setValues(JSON.parse(saved)); setError(null); }}>Discard</Button>}
          <Button type="submit" variant="primary" busy={busy} disabled={!dirty}>Save changes</Button>
        </div>
      </form>
    </>
  );
}
