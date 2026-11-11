// Plain views over the API's JSON.
class Residency {
  Residency(this.json);
  final Map<String, dynamic> json;
  int get id => json['id'] as int;
  int get unit => json['unit'] as int;
  int get condominium => json['condominium'] as int;
  String get condominiumName => json['condominium_name'] as String? ?? '';
  String get unitDisplay => json['unit_display'] as String? ?? '';
  bool get active => json['is_active'] as bool? ?? true;
  bool get receivesCalls => json['receives_intercom_calls'] as bool? ?? true;
  /// The site uses the resident app (the platform administrator can turn it off per site).
  bool get appEnabled => json['resident_app_enabled'] as bool? ?? true;
  /// Modules of the site's plan; servers before plans send none, which means everything.
  bool hasModule(String key) => (json['modules'] as List?)?.contains(key) ?? true;
}

class Me {
  Me(this.json) {
    final active = ((json['residencies'] as List?) ?? []).cast<Map<String, dynamic>>().map(Residency.new).where((r) => r.active);
    residencies = active.where((r) => r.appEnabled).toList();
    appOffAtSite = residencies.isEmpty && active.isNotEmpty;
  }
  final Map<String, dynamic> json;
  late final List<Residency> residencies;
  /// Linked to a unit, but at a site that does not use the resident app.
  late final bool appOffAtSite;
  int get id => json['id'] as int;
  String get username => json['username'] as String;
  String get firstName => json['first_name'] as String? ?? '';
  String get displayName {
    final full = '${json['first_name'] ?? ''} ${json['last_name'] ?? ''}'.trim();
    return full.isEmpty ? username : full;
  }
}

class Invitation {
  Invitation(this.json);
  final Map<String, dynamic> json;
  int get id => json['id'] as int;
  String get visitorName => json['visitor_name'] as String;
  String get visitorPhone => json['visitor_phone'] as String? ?? '';
  String get unitDisplay => json['unit_display'] as String? ?? '';
  String get purpose => json['purpose'] as String;
  String get status => json['status'] as String;
  String get shareUrl => json['share_url'] as String;
  String get plate => json['vehicle_plate'] as String? ?? '';
  int get maxEntries => json['max_entries'] as int;
  int get entryCount => json['entry_count'] as int;
  DateTime get validFrom => DateTime.parse(json['valid_from'] as String).toLocal();
  DateTime get validUntil => DateTime.parse(json['valid_until'] as String).toLocal();
}

class Vehicle {
  Vehicle(this.json);
  final Map<String, dynamic> json;
  int get id => json['id'] as int;
  String get plate => json['plate_number'] as String;
  String get unitDisplay => json['unit_display'] as String? ?? '';
  String get description => [json['colour'], json['make'], json['model']].where((v) => v != null && '$v'.isNotEmpty).join(' ');
}

class AccessEntry {
  AccessEntry(this.json);
  final Map<String, dynamic> json;
  String get result => json['result'] as String;
  String get method => json['method'] as String;
  String get gate => json['gate_name'] as String? ?? '';
  String get plate => json['plate_number'] as String? ?? '';
  String get visitor => json['visitor_name'] as String? ?? '';
  String get actor => json['actor_name'] as String? ?? '';
  String get reason => json['reason'] as String? ?? '';
  DateTime get at => DateTime.parse(json['occurred_at'] as String).toLocal();
}

class IntercomCall {
  IntercomCall(this.json);
  final Map<String, dynamic> json;
  int get id => json['id'] as int;
  String get status => json['status'] as String;
  bool get isOpen => json['is_open'] as bool? ?? false;
  String get unitDisplay => json['unit_display'] as String? ?? '';
  String get kioskName => json['kiosk_name'] as String? ?? '';
  String get visitorName => json['visitor_name'] as String? ?? '';
  String get visitorPhone => json['visitor_phone'] as String? ?? '';
  String get visitorCompany => json['visitor_company'] as String? ?? '';
  String get visitorPurpose => visitPurposeLabel[json['visitor_purpose']] ?? '';

  /// "Parcel delivery · Ninja Van"
  String get purposeLine => [visitorPurpose, visitorCompany].where((s) => s.isNotEmpty).join(' · ');
  bool get hasSnapshot => json['has_snapshot'] as bool? ?? false;
  DateTime get createdAt => DateTime.parse(json['created_at'] as String).toLocal();
}

const methodLabel = {'lpr': 'Licence plate', 'qr': 'Invitation QR', 'intercom': 'Intercom', 'app': 'App', 'manual': 'Guardhouse'};
const visitPurposeLabel = {
  'guest': 'Guest', 'delivery': 'Parcel delivery', 'food': 'Food delivery', 'contractor': 'Contractor',
  'pickup': 'Pick-up / drop-off', 'other': 'Other',
};
const purposeLabel = {'guest': 'Guest', 'delivery': 'Delivery', 'contractor': 'Contractor', 'pickup': 'Pick-up / drop-off', 'other': 'Other'};

class Gate {
  Gate(this.json);
  final Map<String, dynamic> json;
  int get id => json['id'] as int;
  String get name => json['name'] as String;
  String get type => json['gate_type'] as String? ?? 'vehicle';
  bool get active => json['is_active'] as bool? ?? true;
}

double _money(Object? v) => double.tryParse('$v') ?? 0;

class Facility {
  Facility(this.json);
  final Map<String, dynamic> json;
  int get id => json['id'] as int;
  String get name => json['name'] as String;
  String get description => json['description'] as String? ?? '';
  String get location => json['location'] as String? ?? '';
  String get icon => json['icon'] as String? ?? 'event';
  bool get hasImage => json['has_image'] as bool? ?? false;
  int get capacity => json['capacity'] as int? ?? 1;
  String get opensAt => (json['opens_at'] as String? ?? '').padRight(5).substring(0, 5);
  String get closesAt => (json['closes_at'] as String? ?? '').padRight(5).substring(0, 5);
  int get slotMinutes => json['slot_minutes'] as int? ?? 60;
  int get maxSlots => json['max_slots_per_booking'] as int? ?? 1;
  double get pricePerSlot => _money(json['price_per_slot']);
  double get deposit => _money(json['deposit']);
  bool get isPaid => json['is_paid'] as bool? ?? false;
  int get advanceDays => json['advance_days'] as int? ?? 14;
  int get cancelHours => json['cancel_hours'] as int? ?? 24;
  String get rules => json['rules'] as String? ?? '';
  int get condominium => json['condominium'] as int;
  String get priceLabel => isPaid
      ? '\$${pricePerSlot.toStringAsFixed(2)} / ${slotMinutes >= 60 && slotMinutes % 60 == 0 ? '${slotMinutes ~/ 60} h' : '$slotMinutes min'}'
      : 'Free';
}

class Slot {
  Slot(this.json);
  final Map<String, dynamic> json;
  /// The start as the server wrote it, sent back unchanged when booking.
  String get raw => json['starts_at'] as String;
  DateTime get startsAt => DateTime.parse(json['starts_at'] as String).toLocal();
  DateTime get endsAt => DateTime.parse(json['ends_at'] as String).toLocal();
  bool get available => json['available'] as bool? ?? false;
  int get left => json['left'] as int? ?? 0;
}

class Booking {
  Booking(this.json);
  final Map<String, dynamic> json;
  int get id => json['id'] as int;
  String get facilityName => json['facility_name'] as String? ?? '';
  String get facilityIcon => json['facility_icon'] as String? ?? 'event';
  String get unitDisplay => json['unit_display'] as String? ?? '';
  DateTime get startsAt => DateTime.parse(json['starts_at'] as String).toLocal();
  DateTime get endsAt => DateTime.parse(json['ends_at'] as String).toLocal();
  int get guests => json['guests'] as int? ?? 1;
  String get status => json['status'] as String;
  String get statusDisplay => json['status_display'] as String? ?? status;
  String get paymentStatus => json['payment_status'] as String? ?? 'none';
  String get paymentStatusDisplay => json['payment_status_display'] as String? ?? paymentStatus;
  double get amount => _money(json['amount']);
  double get deposit => _money(json['deposit']);
  String get currency => json['currency'] as String? ?? 'SGD';
  String get cancelReason => json['cancel_reason'] as String? ?? '';
  bool get canCancel => json['can_cancel'] as bool? ?? false;
  bool get awaitingPayment => status == 'pending_payment';
  bool get upcoming => endsAt.isAfter(DateTime.now()) && (status == 'confirmed' || status == 'pending_payment');
}

class Visit {
  Visit(this.json);
  final Map<String, dynamic> json;
  int get id => json['id'] as int;
  String get passNumber => json['pass_number'] as String? ?? '';
  String get visitorName => json['visitor_name'] as String? ?? '';
  String get purpose => visitPurposeLabel[json['purpose']] ?? '';
  String get company => json['company'] as String? ?? '';
  String get plate => json['vehicle_plate'] as String? ?? '';
  String get source => json['source_display'] as String? ?? '';
  String get state => json['state'] as String? ?? '';
  String get unitDisplay => json['unit_display'] as String? ?? '';
  DateTime get checkIn => DateTime.parse(json['created_at'] as String).toLocal();
  DateTime? get checkOut => json['checked_out_at'] == null ? null : DateTime.parse(json['checked_out_at'] as String).toLocal();
}

class FeedbackItem {
  FeedbackItem(this.json);
  final Map<String, dynamic> json;
  int get id => json['id'] as int;
  int get rating => json['rating'] as int;
  String get category => json['category_display'] as String? ?? '';
  String get comment => json['comment'] as String? ?? '';
  String get status => json['status'] as String? ?? 'new';
  String get statusDisplay => json['status_display'] as String? ?? '';
  String get reply => json['reply'] as String? ?? '';
  String get repliedBy => json['replied_by_name'] as String? ?? '';
  DateTime get createdAt => DateTime.parse(json['created_at'] as String).toLocal();
}

const feedbackCategories = {
  'security': 'Security', 'cleanliness': 'Cleanliness', 'facilities': 'Facilities', 'maintenance': 'Maintenance',
  'management': 'Management office', 'app': 'Elix app', 'other': 'Other',
};

/// One entry of the resident's notification feed (/v1/notifications/).
class NotificationItem {
  NotificationItem(this.json);
  final Map<String, dynamic> json;
  String get id => json['id'] as String;
  String get kind => json['kind'] as String;
  String get title => json['title'] as String;
  String get body => json['body'] as String? ?? '';
  DateTime get at => DateTime.parse(json['at'] as String).toLocal();
}

/// Current weather at the condo (NEA via the server).
class Weather {
  Weather(this.json);
  final Map<String, dynamic> json;
  double? get temperature => (json['temperature'] as num?)?.toDouble();
  double? get humidity => (json['humidity'] as num?)?.toDouble();
  String get forecast => json['forecast'] as String? ?? '';
  String get area => json['area'] as String? ?? '';
}

/// A file the management keeps for the resident (/v1/resident-documents/): ownership, tenancy…
class ResidentDocument {
  ResidentDocument(this.json);
  final Map<String, dynamic> json;
  int get id => json['id'] as int;
  String get kind => json['kind'] as String? ?? 'other';
  String get title => json['title'] as String? ?? '';
  String get fileName => json['file_name'] as String? ?? 'document';
  String get unitDisplay => json['unit_display'] as String? ?? '';
  int get size => json['size'] as int? ?? 0;
  DateTime get createdAt => DateTime.parse(json['created_at'] as String).toLocal();
  bool get isImage => RegExp(r'\.(jpe?g|png)$', caseSensitive: false).hasMatch(fileName);
}
