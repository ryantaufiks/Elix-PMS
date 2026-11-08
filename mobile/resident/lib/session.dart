import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'api.dart';
import 'models.dart';
import 'push.dart';
import 'realtime.dart';

/// Who is signed in. Residents only: staff use the web dashboard.
class Session extends ChangeNotifier {
  Session._();
  static final instance = Session._();

  Me? me;
  bool loading = true;

  static const _storage = FlutterSecureStorage();

  /// Signed-in users open straight onto the last known profile; it is refreshed from the server
  /// in the background, so a slow or missing network never holds up the first screen.
  Future<void> restore() async {
    await Api.instance.load();
    Api.instance.onSignedOut = _signedOut;
    if (Api.instance.signedIn) {
      final cached = await _storage.read(key: 'me');
      if (cached != null) {
        me = Me(jsonDecode(cached) as Map<String, dynamic>);
        Realtime.instance.start();
      }
      loading = false;
      notifyListeners();
      try {
        await _loadMe();
        notifyListeners();
      } on ApiException catch (e) {
        if (e.status == 403) await logout();
      } catch (_) {
        // Offline: keep the cached profile; the next action retries.
      }
    }
    loading = false;
    notifyListeners();
  }

  Future<void> _loadMe() async {
    final data = await Api.instance.get('/v1/auth/me/') as Map<String, dynamic>;
    await _storage.write(key: 'me', value: jsonEncode(data));
    final user = Me(data);
    if (user.residencies.isEmpty) {
      await Api.instance.clear();
      throw ApiException(403, 'This account is not linked to any unit. Ask your condo management to add you.');
    }
    me = user;
    Realtime.instance.start();
    Push.instance.register();
  }

  Future<void> login(String username, String password) async {
    await Api.instance.login(username, password);
    await _loadMe();
    notifyListeners();
  }

  Future<void> logout() async {
    await Push.instance.unregister();
    Realtime.instance.stop();
    await Api.instance.signOut();
    me = null;
    notifyListeners();
  }

  void _signedOut() {
    Realtime.instance.stop();
    me = null;
    notifyListeners();
  }
}
