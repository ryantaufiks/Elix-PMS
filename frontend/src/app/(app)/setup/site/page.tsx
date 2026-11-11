"use client";

import { useEffect, useState } from "react";

import { FormFields, initialValues } from "@/components/forms";
import { Button, Card, CardHeader, Empty, ErrorNote, PageHeader, useToast } from "@/components/ui";
import { api, ApiError, errorMessage } from "@/lib/api";
import { PlanSummary } from "@/components/PlanSummary";
import { condoFields } from "@/lib/fields";
import { useSession } from "@/lib/session";
import type { Condominium } from "@/lib/types";

export default function SiteSettingsPage() {
  const { condo, isAdmin, me, reload } = useSession();
  const toast = useToast();
  const fields = condoFields({ superuser: me.is_superuser, creating: false });
  const [values, setValues] = useState(() => initialValues(fields, condo));
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => setValues(initialValues(fields, condo)), [condo.id]);

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
      <div className="mb-6"><PlanSummary condoId={condo.id} /></div>
      <Card className="max-w-4xl">
        <CardHeader title="Condominium" />
        <form onSubmit={save} className="space-y-5 p-5 sm:p-6">
          <ErrorNote error={Object.keys(errors).length ? null : error} />
          <FormFields fields={fields} values={values} errors={errors} record={condo} onChange={(n, v) => setValues((s) => ({ ...s, [n]: v }))} />
          <div className="flex justify-end border-t border-line pt-5">
            <Button type="submit" variant="primary" busy={busy}>Save changes</Button>
          </div>
        </form>
      </Card>
    </>
  );
}
