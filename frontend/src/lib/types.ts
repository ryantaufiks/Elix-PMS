export type Page<T> = { count: number; next: string | null; previous: string | null; results: T[] };

export type Role = "admin" | "staff" | "security";

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

export type ResidentDocument = {
  id: number;
  residency: number;
  unit_display: string;
  resident_name: string;
  kind: "ownership" | "tenancy" | "identity" | "other";
  title: string;
  file_name: string;
  size: number;
  uploaded_by_name: string;
  created_at: string;
};

export type Backup = {
  id: number;
  kind: "platform" | "site";
  condominium: number | null;
  condominium_name: string;
  status: "pending" | "running" | "ready" | "failed";
  file_name: string;
  size: number;
  error: string;
  automatic: boolean;
  created_by_name: string;
  created_at: string;
  finished_at: string | null;
  expires_at: string;
  downloads: { user_name: string; ip: string | null; at: string }[];
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
  /** Modules the site's subscription includes (core.entitlements). */
  modules: string[];
  plan_name: string;
  subscription_status: SubscriptionStatus | "";
  /** Trial end, paid-until or grace end, whichever applies to the status. */
  subscription_ends_on: string | null;
  lpr_enabled: boolean;
  invitation_max_days: number;
  intercom_ring_timeout_seconds: number;
  face_verification_enabled: boolean;
  visitor_data_retention_days: number;
  kiosk_visitor_form: boolean;
  kiosk_photo_required: boolean;
  kiosk_walk_in: boolean;
  kiosk_walk_in_photo: boolean;
  kiosk_call_guardhouse: boolean;
  overstay_delivery_minutes: number;
  overstay_guest_minutes: number;
  overstay_contractor_until: string | null;
  season_parking_enabled: boolean;
  season_parking_fee: string;
  season_parking_quota: number;
  visitor_privacy_notice: string;
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
  has_openai_api_key: boolean;
  assistant_mode: "pipeline" | "realtime";
  assistant_chat_model: string;
  assistant_transcribe_model: string;
  assistant_tts_model: string;
  assistant_realtime_model: string;
  assistant_voice: string;
  assistant_max_session_seconds: number;
  assistant_daily_sessions: number;
  ai_usd_per_million_input: string | null;
  ai_usd_per_million_output: string | null;
  smtp_host: string;
  smtp_port: number | null;
  smtp_security: "" | "starttls" | "ssl" | "none";
  smtp_username: string;
  has_smtp_password: boolean;
  email_from_address: string;
  email_from_name: string;
  email_reply_to: string;
  livekit_configured: boolean;
  fcm_configured: boolean;
  openai_configured: boolean;
  email_configured: boolean;
  sources: Record<string, "admin" | ".env" | "">;
  updated_at: string | null;
};

export type SubscriptionStatus = "trial" | "active" | "grace" | "suspended" | "cancelled";

export type ModuleInfo = { key: string; name: string; description: string; requires: string[]; available: boolean; upsell_plan: string };
export type LimitInfo = { key: string; name: string; unit: string; enforced: boolean; metered: boolean };
export type ModuleCatalogue = { modules: ModuleInfo[]; limits: LimitInfo[] };

export type Plan = {
  id: number;
  code: string;
  name: string;
  description: string;
  modules: string[];
  limits: Record<string, number | null>;
  overage_rates: Record<string, number>;
  currency: string;
  sort_order: number;
  is_public: boolean;
  is_active: boolean;
  subscriptions: number;
  updated_at: string;
};

export type Subscription = {
  condominium: number;
  condominium_name: string;
  plan: number;
  plan_name: string;
  addons: string[];
  disabled_modules: string[];
  limit_overrides: Record<string, number | null>;
  status: SubscriptionStatus;
  trial_ends_on: string | null;
  period_ends_on: string | null;
  grace_ends_on: string | null;
  billing_name: string;
  billing_email: string;
  notes?: string;
  modules: string[];
  limits: Record<string, number | null>;
  usage: Record<string, number>;
  events?: { id: number; at: string; actor_name: string; summary: string }[];
  updated_at: string;
};

export type UsageRow = {
  site: string; site_id: number; code: string; plan: string; status: string; currency: string;
  intercom_minutes: number; intercom_minutes_allowed: number | null; intercom_minutes_overage: number; intercom_minutes_amount: number;
  ai_conversations: number; ai_conversations_allowed: number | null; ai_conversations_overage: number; ai_conversations_amount: number;
  ai_conversations_own_key: number; ai_tokens_in: number; ai_tokens_out: number; ai_cost_usd: number | null; overage_amount: number;
};

export type EmailLog = {
  id: number;
  condominium: number | null;
  condominium_name: string;
  to: string;
  subject: string;
  template: string;
  status: "queued" | "sent" | "failed";
  attempts: number;
  error: string;
  created_at: string;
  sent_at: string | null;
};

export type AssistantSettings = {
  condominium: number;
  enabled: boolean;
  name: string;
  greeting: string;
  languages: string;
  instructions: string;
  has_openai_api_key: boolean;
  updated_at: string;
};

export type AssistantModule = { id: number; condominium: number; title: string; content: string; order: number; is_active: boolean };

export type AssistantMap = { id: number; condominium: number; name: string; description: string; has_image: boolean; order: number; is_active: boolean };

export type AssistantAction =
  | { type: "show_map"; map_id: number }
  | { type: "start_walk_in"; unit: string; visitor_name: string; purpose: string; company: string }
  | { type: "call_resident"; unit: string }
  | { type: "open_screen"; screen: "invitation" | "checkout" }
  | { type: "call_guardhouse" }
  | { type: "end_conversation" };

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
  resident_remote_open: boolean;
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
  /** Null for a call to the guardhouse (unit_display is then "Guardhouse"). */
  unit: number | null;
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
  kind: "resident" | "season" | "temporary";
  kind_display: string;
  holder_name: string;
  valid_from: string | null;
  valid_until: string | null;
  status: "active" | "expiring" | "expired" | "upcoming" | "inactive";
};

export type ParkingPermit = {
  id: number;
  condominium: number;
  unit: number;
  unit_display: string;
  bought_by: string;
  vehicle: number | null;
  plate_number: string;
  holder_name: string;
  months: number;
  starts_on: string;
  ends_on: string;
  status: "pending_payment" | "paid" | "expired" | "cancelled";
  status_display: string;
  amount: string;
  currency: string;
  payment_expires_at: string | null;
  paid_at: string | null;
  created_at: string;
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
  prints_slips: boolean;
  token_hint: string;
  last_seen_at: string | null;
  app_version: string;
};

export type VisitState = "on_site" | "checked_out" | "expired";
export type VisitSource = "kiosk" | "staff" | "invitation" | "intercom";

export type Visit = {
  id: number;
  condominium: number;
  unit: number;
  unit_display: string;
  source: VisitSource;
  source_display: string;
  kiosk: number | null;
  kiosk_name: string;
  gate: number | null;
  gate_name: string;
  invitation: number | null;
  intercom_call: number | null;
  visitor: number | null;
  visitor_name: string;
  visitor_phone: string;
  visitor_blocked: boolean;
  purpose: string;
  company: string;
  vehicle_plate: string;
  notes: string;
  has_snapshot: boolean;
  pass_number: string;
  pin: string;
  issued_on: string;
  valid_until: string;
  state: VisitState;
  checked_out_at: string | null;
  checked_out_by: number | null;
  checked_out_by_name: string;
  created_by: number | null;
  created_by_name: string;
  created_at: string;
  /** When the visitor passes the site's limit for their purpose (null: no limit). */
  overstay_at: string | null;
  overstaying: boolean;
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
  visitors: {
    on_site: number;
    on_site_by_purpose: Record<string, number>;
    cars_on_site: number;
    vehicle_passes_expiring: number;
    overstaying: number;
    arrived_today: number;
    arrived_yesterday_by_now: number;
    left_today: number;
    hourly: { hour: number; arrived: number; left: number }[];
    limits: { delivery_minutes: number; guest_minutes: number; contractor_until: string | null };
  };
};

export type Facility = {
  id: number;
  condominium: number;
  name: string;
  description: string;
  location: string;
  icon: string;
  has_image: boolean;
  capacity: number;
  opens_at: string;
  closes_at: string;
  open_days: number[];
  slot_minutes: number;
  max_slots_per_booking: number;
  concurrent_bookings: number;
  price_per_slot: string;
  deposit: string;
  is_paid: boolean;
  advance_days: number;
  max_upcoming_per_unit: number;
  cancel_hours: number;
  rules: string;
  /** Door opened when the resident checks in at the kiosk. */
  gate: number | null;
  is_active: boolean;
};

export type BookingStatus = "pending_payment" | "confirmed" | "cancelled" | "expired";
export type PaymentStatus = "none" | "pending" | "paid" | "failed" | "refunded";
export type Booking = {
  id: number;
  condominium: number;
  facility: number;
  facility_name: string;
  unit: number;
  unit_display: string;
  booked_by: string;
  starts_at: string;
  ends_at: string;
  slots: number;
  guests: number;
  notes: string;
  status: BookingStatus;
  status_display: string;
  amount: string;
  deposit: string;
  currency: string;
  payment_status: PaymentStatus;
  payment_status_display: string;
  paid_at: string | null;
  cancelled_at: string | null;
  cancel_reason: string;
  created_at: string;
  checked_in_at: string | null;
};

export type PaymentSettings = {
  condominium: number;
  enabled: boolean;
  sandbox: boolean;
  has_hitpay_api_key: boolean;
  has_hitpay_salt: boolean;
  currency: string;
  payment_minutes: number;
  webhook_url: string;
};

export type Feedback = {
  id: number;
  condominium: number;
  unit: number | null;
  unit_display: string;
  resident_name: string;
  rating: number;
  category: string;
  category_display: string;
  comment: string;
  status: "new" | "in_progress" | "resolved";
  status_display: string;
  reply: string;
  replied_by_name: string;
  replied_at: string | null;
  created_at: string;
};
export type FeedbackSummary = { count: number; average: number | null; by_rating: Record<string, number>; open: number };
