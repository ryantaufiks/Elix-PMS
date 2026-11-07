"use client";

import useSWR from "swr";

import { ApiError, errorMessage } from "@/lib/api";

import { EntityModal, type FieldDef } from "./forms";
import { ErrorNote, Loading, Modal } from "./ui";

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
