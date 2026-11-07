// Plain views over the API's JSON.
class Residency {
  Residency(this.json);
  final Map<String, dynamic> json;
  int get id => json['id'] as int;
  int get unit => json['unit'] as int;
  int get condominium => json['condominium'] as int;
  String get unitDisplay => json['unit_display'] as String? ?? '';
  bool get active => json['is_active'] as bool? ?? true;
  bool get receivesCalls => json['receives_intercom_calls'] as bool? ?? true;
}

class Me {
  Me(this.json) : residencies = ((json['residencies'] as List?) ?? []).cast<Map<String, dynamic>>().map(Residency.new).where((r) => r.active).toList();
  final Map<String, dynamic> json;
  final List<Residency> residencies;
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
  bool get hasSnapshot => json['has_snapshot'] as bool? ?? false;
  DateTime get createdAt => DateTime.parse(json['created_at'] as String).toLocal();
}

const methodLabel = {'lpr': 'Licence plate', 'qr': 'Invitation QR', 'intercom': 'Intercom', 'app': 'App', 'manual': 'Guardhouse'};
const purposeLabel = {'guest': 'Guest', 'delivery': 'Delivery', 'contractor': 'Contractor', 'pickup': 'Pick-up / drop-off', 'other': 'Other'};
