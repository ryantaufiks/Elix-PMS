import 'dart:async';
import 'dart:ui';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_callkit_incoming/entities/entities.dart';
import 'package:flutter_callkit_incoming/flutter_callkit_incoming.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'api.dart';
import 'config.dart';

/// CallKit-style ids must be UUIDs; derive a stable one from the call id.
String callUuid(int callId) => '00000000-0000-4000-8000-${callId.toRadixString(16).padLeft(12, '0')}';
int? callIdFromUuid(String? uuid) => uuid == null ? null : int.tryParse(uuid.split('-').last, radix: 16);

/// Native full-screen incoming call (lock screen, ringtone) for a push received in the background.
Future<void> showIncomingCall(Map<String, dynamic> data) async {
  final callId = int.parse('${data['call_id']}');
  final timeout = int.tryParse('${data['timeout'] ?? 45}') ?? 45;
  final visitor = '${data['visitor'] ?? ''}'.trim();
  final purpose = ['${data['purpose'] ?? ''}', '${data['company'] ?? ''}'].where((s) => s.trim().isNotEmpty).join(' · ');
  await FlutterCallkitIncoming.showCallkitIncoming(CallKitParams(
    id: callUuid(callId),
    nameCaller: visitor.isEmpty ? 'Visitor at ${data['kiosk']}' : visitor,
    appName: 'Elix',
    handle: [if (purpose.isNotEmpty) purpose, '${data['kiosk']}', '${data['unit']}'].join(' · '),
    type: 1,
    duration: timeout * 1000,
    extra: {'call_id': callId},
    missedCallNotification: const NotificationParams(showNotification: true, subtitle: 'Missed visitor call', isShowCallback: false),
    android: const AndroidParams(
      isCustomNotification: true,
      isShowLogo: false,
      ringtonePath: 'system_ringtone_default',
      backgroundColor: '#0B1631',
      actionColor: '#2F6FFF',
      incomingCallNotificationChannelName: 'Visitor calls',
      textAccept: 'Answer',
      textDecline: 'Decline',
      isShowFullLockedScreen: true,
    ),
  ));
}

const _acceptedKey = 'accepted_call';

/// Remember that "Answer" was pressed on the native call screen, for the app to pick up when it opens.
Future<void> rememberAccepted(int callId) =>
    const FlutterSecureStorage().write(key: _acceptedKey, value: '$callId:${DateTime.now().millisecondsSinceEpoch}');

/// The call answered on the native screen in the last 2 minutes, if any (read once).
Future<int?> takeAccepted() async {
  const storage = FlutterSecureStorage();
  final value = await storage.read(key: _acceptedKey);
  if (value == null) return null;
  await storage.delete(key: _acceptedKey);
  final parts = value.split(':');
  final at = DateTime.fromMillisecondsSinceEpoch(int.tryParse(parts.last) ?? 0);
  return DateTime.now().difference(at) < const Duration(minutes: 2) ? int.tryParse(parts.first) : null;
}

/// Native call-screen buttons pressed while the app is closed: Decline goes straight to the server
/// (so the kiosk stops ringing); Answer is remembered for the app, which the button also opens.
@pragma('vm:entry-point')
Future<void> callkitBackgroundHandler(CallEvent event) async {
  DartPluginRegistrant.ensureInitialized();
  if (event is CallEventActionCallAccept) {
    final id = callIdFromUuid(event.callKitParams.id);
    if (id != null) await rememberAccepted(id);
    return;
  }
  if (event is! CallEventActionCallDecline) return;
  final id = callIdFromUuid(event.callKitParams.id);
  if (id == null) return;
  await Api.instance.load();
  try {
    await Api.instance.post('/v1/intercom-calls/$id/reject/');
  } catch (_) {}
}

@pragma('vm:entry-point')
Future<void> firebaseBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp();
  final data = message.data;
  if (data['type'] == 'intercom_call') {
    await showIncomingCall(data);
  } else if (data['type'] == 'intercom_call_ended') {
    await FlutterCallkitIncoming.endCall(callUuid(int.parse('${data['call_id']}')));
  }
}

/// Firebase Cloud Messaging: registers this phone with the server so calls ring while the app is closed.
/// Optional: without google-services.json the app works and rings only while open.
class Push {
  Push._();
  static final instance = Push._();

  bool available = false;
  int? _deviceId;
  final _foreground = StreamController<Map<String, dynamic>>.broadcast();
  Stream<Map<String, dynamic>> get foregroundMessages => _foreground.stream;

  Future<void> init() async {
    try {
      await Firebase.initializeApp();
      FirebaseMessaging.onBackgroundMessage(firebaseBackgroundHandler);
      await FlutterCallkitIncoming.onBackgroundMessage(callkitBackgroundHandler);
      FirebaseMessaging.onMessage.listen((m) => _foreground.add(m.data));
      FirebaseMessaging.instance.onTokenRefresh.listen((_) => register());
      available = true;
    } catch (e) {
      debugPrint('Push disabled: $e');
    }
  }

  Future<void> register() async {
    if (!available) return;
    try {
      await FirebaseMessaging.instance.requestPermission();
      await FlutterCallkitIncoming.requestNotificationPermission({
        'title': 'Notifications',
        'rationaleMessagePermission': 'Allow notifications so visitor calls can ring this phone.',
        'postNotificationMessageRequired': 'Allow notifications in Settings so visitor calls can ring this phone.',
      });
      await FlutterCallkitIncoming.requestFullIntentPermission();
      final token = await FirebaseMessaging.instance.getToken();
      if (token == null) return;
      final device = await Api.instance.post('/v1/push-devices/', {'platform': 'android', 'token': token, 'app_version': appVersion});
      _deviceId = (device as Map)['id'] as int?;
    } catch (e) {
      debugPrint('Push registration failed: $e');
    }
  }

  Future<void> unregister() async {
    final id = _deviceId;
    if (id == null) return;
    try {
      await Api.instance.delete('/v1/push-devices/$id/');
    } catch (_) {}
    _deviceId = null;
  }
}
