import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Light, dark or the phone's setting, chosen in Profile and remembered on this phone.
class Appearance extends ChangeNotifier {
  Appearance._();
  static final instance = Appearance._();

  static const _storage = FlutterSecureStorage();
  static const _key = 'theme_mode';

  ThemeMode mode = ThemeMode.system;

  Future<void> restore() async {
    final saved = await _storage.read(key: _key);
    mode = ThemeMode.values.firstWhere((m) => m.name == saved, orElse: () => ThemeMode.system);
    notifyListeners();
  }

  Future<void> set(ThemeMode value) async {
    mode = value;
    notifyListeners();
    await _storage.write(key: _key, value: value.name);
  }
}
