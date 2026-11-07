export type Page<T> = { count: number; next: string | null; previous: string | null; results: T[] };

export type Role = "admin" | "security";

export type UserSummary = {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
};

export type StaffAssignment = { id: number; user: number; condominium: number; role: Role };

export type Residency = {
  id: number;
  user: number;
  user_detail: UserSummary;
  unit: number;
  unit_display: string;
  condominium: number;
  resident_type: "owner" | "tenant" | "family" | "helper";
  is_primary_contact: boolean;
  receives_intercom_calls: boolean;
  is_active: boolean;
};

export type Me = UserSummary & {
  is_superuser: boolean;
  staff_assignments: StaffAssignment[];
  residencies: Residency[];
};

export type Condominium = {
  id: number;
  name: string;
  code: string;
  address: string;
  postal_code: string;
  contact_phone: string;
  is_active: boolean;
  lpr_enabled: boolean;
  invitation_max_days: number;
  intercom_ring_timeout_seconds: number;
  face_verification_enabled: boolean;
  visitor_data_retention_days: number;
  kiosk_visitor_form: boolean;
  kiosk_photo_required: boolean;
  visitor_privacy_notice: string;
};

export type Visitor = {
  id: number;
  condominium: number;
  full_name: string;
  phone: string;
  id_partial: string;
  company: string;
  face_consent_at: string | null;
  last_visit_at: string | null;
  is_blacklisted: boolean;
  blacklist_reason: string;
  created_at: string;
};

export type Block = { id: number; condominium: number; name: string };

export type ManagedUser = UserSummary & {
  is_active: boolean;
  is_superuser: boolean;
  last_login: string | null;
  has_password: boolean;
  residencies: Residency[];
  staff_assignments: StaffAssignment[];
};

export type StaffRow = StaffAssignment & { user_detail: UserSummary; created_at: string };

export type IntegrationAccount = {
  id: number;
  condominium: number;
  provider: "ewelink" | "shelly";
  label: string;
  is_active: boolean;
  notes: string;
  ewelink_region: string;
  ewelink_app_id: string;
  ewelink_account: string;
  ewelink_token_expires_at: string | null;
  shelly_server_uri: string;
  [key: `has_${string}`]: boolean;
};

export type SystemSettings = {
  livekit_url: string;
  livekit_api_key: string;
  livekit_token_ttl_seconds: number | null;
  intercom_unlock_window_seconds: number | null;
  relay_http_timeout: number | null;
  lpr_debounce_seconds: number | null;
  has_livekit_api_secret: boolean;
  has_fcm_service_account_json: boolean;
  livekit_configured: boolean;
  fcm_configured: boolean;
  sources: Record<string, "admin" | ".env" | "">;
  updated_at: string | null;
};

export type Unit = {
  id: number;
  condominium: number;
  block: number | null;
  floor: string;
  unit_number: string;
  label: string;
  display_name: string;
  is_active: boolean;
};

export type Gate = {
  id: number;
  condominium: number;
  name: string;
  gate_type: "vehicle" | "pedestrian" | "door";
  direction: "entry" | "exit" | "both";
  is_active: boolean;
  lpr_auto_open_residents: boolean;
  lpr_auto_open_invited: boolean;
};

export type AccessMethod = "lpr" | "qr" | "intercom" | "app" | "manual";
export type AccessResult = "granted" | "denied" | "error";

export type AccessLog = {
  id: number;
  condominium: number;
  gate: number | null;
  gate_name: string;
  occurred_at: string;
  method: AccessMethod;
  result: AccessResult;
  reason: string;
  plate_number: string;
  unit: number | null;
  unit_display: string;
  visitor_name: string;
  actor_name: string;
  intercom_call: number | null;
  invitation: number | null;
  has_snapshot: boolean;
};

export type CallStatus = "ringing" | "answered" | "approved" | "rejected" | "missed" | "cancelled";

export type IntercomCall = {
  id: number;
  condominium: number;
  unit: number;
  unit_display: string;
  kiosk: number | null;
  kiosk_name: string;
  gate: number | null;
  status: CallStatus;
  is_open: boolean;
  visitor_name: string;
  visitor_purpose: string;
  visitor_company: string;
  visitor_phone: string;
  has_snapshot: boolean;
  answered_by: number | null;
  answered_at: string | null;
  decided_at: string | null;
  ended_at: string | null;
  created_at: string;
};

export type LiveKitConnection = { url: string; room: string; token: string };

export type InvitationStatus = "active" | "completed" | "cancelled" | "expired";
export type Purpose = "guest" | "delivery" | "contractor" | "pickup" | "other";

export type Invitation = {
  id: number;
  condominium: number;
  unit: number;
  unit_display: string;
  host: number;
  host_detail: UserSummary;
  visitor_name: string;
  visitor_phone: string;
  purpose: Purpose;
  valid_from: string;
  valid_until: string;
  max_entries: number;
  entry_count: number;
  vehicle_plate: string;
  require_face: boolean;
  gates: number[];
  status: InvitationStatus;
  notes: string;
  share_url: string;
  created_at: string;
};

export type Vehicle = {
  id: number;
  condominium: number;
  unit: number;
  unit_display: string;
  plate_number: string;
  make: string;
  model: string;
  colour: string;
  is_active: boolean;
  notes: string;
};

export type Relay = {
  id: number;
  gate: number;
  name: string;
  provider: "ewelink" | "shelly";
  control_mode: "cloud" | "local" | "local_then_cloud";
  is_active: boolean;
  account: number | null;
  cloud_device_id: string;
  channel: number;
  local_ip: string | null;
  local_port: number | null;
  local_username: string;
  pulse_seconds: number;
  has_local_password: boolean;
  has_local_device_key: boolean;
  last_triggered_at: string | null;
  last_error: string;
};

export type Camera = {
  id: number;
  gate: number;
  name: string;
  device_id: string;
  direction: "entry" | "exit" | "both";
  ip_address: string | null;
  is_active: boolean;
  webhook_username: string;
  has_webhook_password: boolean;
  webhook_url: string;
  plate_field: string;
  api_username: string;
  has_api_password: boolean;
  last_seen_at: string | null;
  last_payload: unknown;
};

export type Kiosk = {
  id: number;
  condominium: number;
  gate: number | null;
  name: string;
  is_active: boolean;
  token_hint: string;
  last_seen_at: string | null;
  app_version: string;
};

export type Summary = {
  granted_today: number;
  denied_today: number;
  errors_today: number;
  invitations_today: number;
  open_calls: number;
  relays_total: number;
  relays_failing: number;
  cameras_total: number;
  cameras_offline: number;
  kiosks_total: number;
  kiosks_offline: number;
  lpr_enabled: boolean | null;
  hourly: { hour: number; granted: number; denied: number; error: number }[];
  by_method: Partial<Record<AccessMethod, number>>;
  gates: { id: number; name: string; gate_type: Gate["gate_type"]; is_active: boolean; relays_total: number; relays_failing: number }[];
};
