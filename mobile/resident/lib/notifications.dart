import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'api.dart';
import 'models.dart';

/// Unread count for the bell on the home screen. "Read" is remembered on this phone.
class NotificationCenter extends ChangeNotifier {
  NotificationCenter._();
  static final instance = NotificationCenter._();

  static const _storage = FlutterSecureStorage();
  static const _key = 'notifications_seen_at';
  static const _checked = 20;

  int unread = 0;
  DateTime? _seenAt;

  /// Count what arrived since the bell was last opened (shown as "20+" beyond one page).
  Future<void> refresh() async {
    try {
      _seenAt ??= DateTime.tryParse(await _storage.read(key: _key) ?? '');
      final rows = await Api.instance.list('/v1/notifications/?page_size=$_checked');
      final seen = _seenAt;
      final count = rows.map(NotificationItem.new).where((n) => seen == null || n.at.isAfter(seen)).length;
      if (count != unread) {
        unread = count;
        notifyListeners();
      }
    } catch (_) {}
  }

  Future<void> markAllRead() async {
    _seenAt = DateTime.now();
    await _storage.write(key: _key, value: _seenAt!.toIso8601String());
    unread = 0;
    notifyListeners();
  }

  DateTime? get seenAt => _seenAt;

  /// Forget the previous user's state (signing out wipes the stored timestamp too).
  void reset() {
    _seenAt = null;
    unread = 0;
  }

  bool get more => unread >= _checked;
}
