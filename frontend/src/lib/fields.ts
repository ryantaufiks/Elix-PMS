// Form definitions shared by several pages.
import type { FieldDef } from "@/components/forms";

const slug = (v: string) => v.toLowerCase().replace(/[^a-z0-9-]+/g, "-").replace(/^-+/, "");

export const condoFields = (opts: { superuser: boolean; creating: boolean }): FieldDef[] => [
  { name: "name", label: "Name", required: true, placeholder: "e.g. The Sail @ Marina Bay" },
  { name: "code", label: "Short code", required: true, transform: slug, hint: "Unique, lowercase, e.g. the-sail.", placeholder: "the-sail" },
  { name: "address", label: "Address", wide: true },
  { name: "postal_code", label: "Postal code", hint: "6 digits", placeholder: "018987" },
  { name: "contact_phone", label: "Management office phone", type: "tel", placeholder: "+65 6123 4567" },
  ...(opts.superuser && !opts.creating ? [{ name: "is_active", label: "Site is active", type: "checkbox" } as FieldDef] : []),
  { name: "lpr_enabled", label: "Licence-plate recognition enabled", type: "checkbox", section: "Access policy", wide: true,
    hint: "When off, camera events are only recorded (useful while setting up cameras)." },
  { name: "intercom_ring_timeout_seconds", label: "Intercom ring timeout (seconds)", type: "number", hint: "After this the call is marked missed." },
  { name: "invitation_max_days", label: "Longest invitation (days)", type: "number" },
  { name: "face_verification_enabled", label: "Allow invitations to require a face check", type: "checkbox", wide: true },
  { name: "visitor_data_retention_days", label: "Keep visitor data for (days)", type: "number", section: "PDPA", hint: "Visitor personal data and photos are deleted after this." },
];

export const condoDefaults = {
  intercom_ring_timeout_seconds: 45, invitation_max_days: 30, visitor_data_retention_days: 90, lpr_enabled: false,
};
