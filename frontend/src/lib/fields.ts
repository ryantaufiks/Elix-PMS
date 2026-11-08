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
  { name: "kiosk_visitor_form", label: "Ask visitors for their details before calling", type: "checkbox", wide: true, section: "Visitor kiosk",
    hint: "Name and purpose; mobile or last 4 of NRIC/FIN are optional and let returning visitors skip the form." },
  { name: "kiosk_photo_required", label: "Take the visitor's photo before calling", type: "checkbox", wide: true,
    hint: "Shown to the resident before they answer, and kept with the call record." },
  { name: "kiosk_walk_in", label: "Offer walk-in registration", type: "checkbox", wide: true,
    hint: "Visitors enter their details, pick the unit and get a printed slip with a pass number (V001, C001, …). The gate does not open: they show the slip to security, and scan its QR at the kiosk when leaving." },
  { name: "kiosk_walk_in_photo", label: "Take the walk-in visitor's photo", type: "checkbox", wide: true,
    hint: "Shown to security on the Visitor list." },
  { name: "kiosk_checkout", label: "Offer self check-out at the kiosk", type: "checkbox", wide: true,
    hint: "Visitors scan the QR or enter the 4-digit PIN from their pass when they leave." },
  { name: "visitor_data_retention_days", label: "Keep visitor data for (days)", type: "number", section: "PDPA",
    hint: "Visitor names, contact details, photos and plates are deleted automatically after this (blacklisted visitors are kept)." },
  { name: "visitor_privacy_notice", label: "Privacy notice shown to visitors", type: "textarea", wide: true,
    hint: "Shown at the kiosk and on visitor passes. Leave blank to use the standard notice, which states the purpose, who sees the data, the retention period and the management office contact." },
];

export const condoDefaults = {
  intercom_ring_timeout_seconds: 45, invitation_max_days: 30, visitor_data_retention_days: 90, lpr_enabled: false,
  kiosk_visitor_form: true, kiosk_photo_required: true, kiosk_walk_in: true, kiosk_walk_in_photo: true, kiosk_checkout: true,
};
