"use client";

import { useState } from "react";
import useSWR from "swr";

import { api, ApiError, errorMessage } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/format";

import { EntityModal, type FieldDef, FormFields, initialValues } from "./forms";
import { Button, ErrorNote, Field, Loading, Modal, Select, useToast } from "./ui";

export const personFields = (creating: boolean): FieldDef[] => [
  { name: "first_name", label: "First name", required: true },
  { name: "last_name", label: "Last name" },
  { name: "phone", label: "Mobile", type: "tel", placeholder: "+65 9123 4567" },
  { name: "email", label: "Email", type: "email" },
  { name: "username", label: "Username", required: true, hint: "Used to sign in to the app.", transform: (v) => v.toLowerCase().replace(/\s+/g, "") },
  ...(creating
    ? [{ name: "password", label: "Initial password", type: "password", hint: "Optional. At least 8 characters; leave blank to set later." } as FieldDef]
    : [{ name: "is_active", label: "Account active (can sign in)", type: "checkbox" } as FieldDef]),
];

export function fieldErrorsOf(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError) || !error.data || typeof error.data !== "object" || Array.isArray(error.data)) return {};
  return Object.fromEntries(
    Object.entries(error.data as Record<string, unknown>).filter(([k]) => !["detail", "non_field_errors", "residency", "staff"].includes(k)).map(([k, v]) => [k, errorMessage(v, "Invalid")]),
  );
}

export function EditPerson({ userId, onClose, onSaved }: { userId: number; onClose: () => void; onSaved: () => void }) {
  const { data, error } = useSWR<Record<string, unknown>>(`/v1/users/${userId}/`);
  if (error) {
    return (
      <Modal open onClose={onClose} title="Edit profile">
        <ErrorNote error={error instanceof ApiError && error.status === 404 ? new Error("You cannot edit this person: they also belong to another condominium or are a platform administrator.") : error} />
      </Modal>
    );
  }
  if (!data) return <Modal open onClose={onClose} title="Edit profile"><Loading /></Modal>;
  return <EntityModal title={`Edit ${String(data.first_name || data.username)}`} fields={personFields(false)} record={data} endpoint={`/v1/users/${userId}/`} onClose={onClose} onSaved={onSaved} />;
}

export function SetPassword({ userId, name, onClose }: { userId: number; name: string; onClose: () => void }) {
  return (
    <EntityModal title={`New password for ${name}`} submitLabel="Set password" fields={[{ name: "password", label: "New password", type: "password", required: true, wide: true, hint: "At least 8 characters, not too common. Tell the person in person or by phone." }]}
      record={null} endpoint={`/v1/users/${userId}/set-password/`} onClose={onClose} onSaved={onClose} />
  );
}

const ROLE_OPTIONS = (["security", "staff", "admin"] as const).map((value) => ({ value, label: ROLE_LABEL[value] }));

/** New staff account at a site: the person's details and their role (Officer, Staff or Site admin). */
export function AddStaff({ condoId, onClose, onDone, role: initialRole = "security", title = "Add staff" }: {
  condoId: number; onClose: () => void; onDone: () => void; role?: "security" | "staff" | "admin"; title?: string;
}) {
  const toast = useToast();
  const fields = personFields(true).map((f) => (f.name === "password" ? { ...f, required: true, hint: "At least 8 characters. Staff sign in to the dashboard with it." } : f));
  const [values, setValues] = useState(() => initialValues(fields, null));
  const [role, setRole] = useState<string>(initialRole);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const errors = fieldErrorsOf(error);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/v1/users/", { method: "POST", body: { ...values, staff: { condominium: condoId, role } } });
      toast("success", role === "admin" ? "Site admin account created." : "Staff account created.");
      onDone();
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <Modal open wide onClose={onClose} title={title} footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" busy={busy} type="submit" form="add-staff">Create account</Button></>}>
      <form id="add-staff" onSubmit={submit} className="space-y-4">
        <ErrorNote error={Object.keys(errors).length ? null : error} />
        <Field label="Role">
          <Select value={role} onChange={(e) => setRole(e.target.value)}>
            {ROLE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </Select>
        </Field>
        <FormFields fields={fields} values={values} errors={errors} onChange={(n, v) => setValues((s) => ({ ...s, [n]: v }))} />
      </form>
    </Modal>
  );
}
