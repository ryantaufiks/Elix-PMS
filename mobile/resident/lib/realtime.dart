import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import 'api.dart';
import 'config.dart';

/// Live events (/ws/events/) for the user's units: access logs and intercom calls. Reconnects with backoff.
class Realtime {
  Realtime._();
  static final instance = Realtime._();

  final _events = StreamController<Map<String, dynamic>>.broadcast();
  Stream<Map<String, dynamic>> get events => _events.stream;

  WebSocketChannel? _channel;
  StreamSubscription? _sub;
  Timer? _retry;
  int _attempt = 0;
  bool _running = false;

  void start() {
    if (_running) return;
    _running = true;
    _connect();
  }

  void stop() {
    _running = false;
    _retry?.cancel();
    _sub?.cancel();
    _channel?.sink.close();
    _channel = null;
  }

  /// Reconnect now (e.g. the app came back to the foreground).
  void kick() {
    if (!_running) return;
    _retry?.cancel();
    _sub?.cancel();
    _channel?.sink.close();
    _attempt = 0;
    _connect();
  }

  Future<void> _connect() async {
    if (!_running) return;
    await Api.instance.refresh(); // sockets cannot refresh mid-way; start with a fresh token
    final token = Api.instance.accessToken;
    if (token == null || !_running) return;
    final url = Uri.parse(apiBase.replaceFirst('http', 'ws')).replace(path: '/ws/events/', queryParameters: {'token': token});
    try {
      final channel = WebSocketChannel.connect(url);
      _channel = channel;
      await channel.ready;
      _attempt = 0;
      _sub = channel.stream.listen(
        (message) {
          try {
            _events.add(jsonDecode(message as String) as Map<String, dynamic>);
          } catch (_) {}
        },
        onDone: _scheduleRetry,
        onError: (_) => _scheduleRetry(),
      );
    } catch (_) {
      _scheduleRetry();
    }
  }

  void _scheduleRetry() {
    if (!_running) return;
    _attempt += 1;
    _retry?.cancel();
    _retry = Timer(Duration(seconds: [1, 2, 4, 8, 16, 30][_attempt.clamp(0, 5)]), _connect);
  }
}
