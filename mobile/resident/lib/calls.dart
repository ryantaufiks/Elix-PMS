import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_callkit_incoming/entities/entities.dart';
import 'package:flutter_callkit_incoming/flutter_callkit_incoming.dart';

import 'api.dart';
import 'models.dart';
import 'push.dart';
import 'realtime.dart';
import 'session.dart';
import 'ui/call_screen.dart';
import 'ui/incoming_call_screen.dart';

final navigatorKey = GlobalKey<NavigatorState>();

/// Routes incoming calls to the right screen, whatever announced them: the WebSocket (app open),
/// a push received in the foreground, or the native call UI after a push in the background.
class Calls {
  Calls._();
  static final instance = Calls._();

  final _shown = <int>{};
  int? _active;
  // Screens requested before the app could show them (launch from the lock screen, still signing in).
  int? _pendingAnswer;
  int? _pendingRing;
  final _updates = StreamController<IntercomCall>.broadcast();
  Stream<IntercomCall> get updates => _updates.stream;

  void start() {
    Realtime.instance.events.listen((event) {
      if (event['type'] != 'intercom_call') return;
      final call = IntercomCall((event['data'] as Map).cast<String, dynamic>());
      _updates.add(call);
      if (call.status == 'ringing' && call.isOpen) _ring(call.id);
      if (!call.isOpen || call.status != 'ringing') FlutterCallkitIncoming.endCall(callUuid(call.id));
    });
    Push.instance.foregroundMessages.listen((data) {
      if (data['type'] == 'intercom_call') _ring(int.parse('${data['call_id']}'));
    });
    FlutterCallkitIncoming.onEvent.listen((CallEvent? event) {
      switch (event) {
        case CallEventActionCallAccept(:final callKitParams):
          final id = callIdFromUuid(callKitParams.id);
          if (id != null) {
            rememberAccepted(id); // in case the screen cannot open yet
            answer(id);
          }
        case CallEventActionCallDecline(:final callKitParams):
          final id = callIdFromUuid(callKitParams.id);
          if (id != null) Api.instance.post('/v1/intercom-calls/$id/reject/').catchError((_) => null);
        default:
          break;
      }
    });
    reconcile();
  }

  bool _reconciling = false;

  /// Called at start-up and whenever the app comes to the front. Whatever happened while it was
  /// closed (Answer or a tap on the call notification, possibly before this code was running), the
  /// app ends up on the right screen: the answered call, or the ringing call's incoming screen.
  Future<void> reconcile() async {
    if (_reconciling || Session.instance.me == null) return;
    _reconciling = true;
    try {
      final accepted = await takeAccepted();
      if (accepted != null) return answer(accepted);
      for (final call in await FlutterCallkitIncoming.activeCalls()) {
        final id = callIdFromUuid(call.id);
        if (id != null && call.isAccepted) return answer(id);
      }
      final me = Session.instance.me!.id;
      for (final row in await Api.instance.list('/v1/intercom-calls/?page_size=10')) {
        final call = IntercomCall(row);
        if (!call.isOpen) continue;
        if (call.status == 'answered' && row['answered_by'] == me) return answer(call.id); // rejoin
        if (call.status == 'ringing') {
          FlutterCallkitIncoming.endCall(callUuid(call.id)); // the in-app screen rings instead
          _ring(call.id);
        }
      }
    } catch (_) {
      // Offline: the next resume tries again.
    } finally {
      _reconciling = false;
    }
  }

  NavigatorState? get _navigator => Session.instance.me == null ? null : navigatorKey.currentState;

  /// Show the in-app incoming call screen (app in the foreground).
  Future<void> _ring(int callId) async {
    if (_shown.contains(callId) || _active == callId) return;
    final navigator = _navigator;
    if (navigator == null) {
      _pendingRing = callId;
      return;
    }
    _shown.add(callId);
    try {
      final call = IntercomCall(await Api.instance.get('/v1/intercom-calls/$callId/') as Map<String, dynamic>);
      if (!call.isOpen || call.status != 'ringing' || _active == callId) return;
      navigator.push(MaterialPageRoute(builder: (_) => IncomingCallScreen(call: call), fullscreenDialog: true));
    } catch (_) {}
  }

  /// Open the call screen (which answers the call). Queued until the app can show it.
  void answer(int callId) {
    if (_active == callId) return;
    _pendingAnswer = callId;
    showPending();
  }

  /// Called once the home screen is up (and after sign-in) to show anything queued.
  void showPending() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final navigator = _navigator;
      if (navigator == null) return;
      final answerId = _pendingAnswer;
      final ringId = _pendingRing;
      _pendingAnswer = _pendingRing = null;
      if (answerId != null && _active != answerId) {
        takeAccepted(); // handled now; do not reopen it on the next resume
        _active = answerId;
        _shown.add(answerId);
        navigator.push(MaterialPageRoute(builder: (_) => CallScreen(callId: answerId)));
      } else if (ringId != null) {
        _ring(ringId);
      }
    });
  }

  void finished(int callId) {
    if (_active == callId) _active = null;
    FlutterCallkitIncoming.endCall(callUuid(callId));
  }
}
