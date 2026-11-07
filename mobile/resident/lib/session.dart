import 'package:flutter/foundation.dart';

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

  Future<void> restore() async {
    await Api.instance.load();
    Api.instance.onSignedOut = _signedOut;
    if (Api.instance.signedIn) {
      try {
        await _loadMe();
      } catch (_) {
        // Offline at start-up: stay signed in and retry on the next action.
      }
    }
    loading = false;
    notifyListeners();
  }

  Future<void> _loadMe() async {
    final data = await Api.instance.get('/v1/auth/me/') as Map<String, dynamic>;
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
    await Api.instance.clear();
    me = null;
    notifyListeners();
  }

  void _signedOut() {
    Realtime.instance.stop();
    me = null;
    notifyListeners();
  }
}
