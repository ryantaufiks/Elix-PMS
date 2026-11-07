import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

import 'config.dart';

class ApiException implements Exception {
  ApiException(this.status, this.message, [this.data]);
  final int status;
  final String message;
  final Object? data;
  @override
  String toString() => message;
}

/// First readable message from a DRF error body ({detail}, {field: [msg]} or [msg]).
String errorMessage(Object? data, String fallback) {
  if (data == null) return fallback;
  if (data is String) return data;
  if (data is List) return data.isEmpty ? fallback : errorMessage(data.first, fallback);
  if (data is Map) {
    if (data['detail'] != null) return errorMessage(data['detail'], fallback);
    if (data.isNotEmpty) {
      final entry = data.entries.first;
      final message = errorMessage(entry.value, fallback);
      return entry.key == 'non_field_errors' ? message : '${entry.key.toString().replaceAll('_', ' ')}: $message';
    }
  }
  return fallback;
}

/// JWT client for the Elix API. Tokens live in the platform keystore; one refresh at a time.
class Api {
  Api._();
  static final instance = Api._();

  static const _storage = FlutterSecureStorage();
  String? _access;
  String? _refresh;
  Future<bool>? _refreshing;
  void Function()? onSignedOut;

  Future<void> load() async {
    _access = await _storage.read(key: 'access');
    _refresh = await _storage.read(key: 'refresh');
  }

  bool get signedIn => _refresh != null;
  String? get accessToken => _access;

  Future<void> _save(String access, [String? refresh]) async {
    _access = access;
    await _storage.write(key: 'access', value: access);
    if (refresh != null) {
      _refresh = refresh;
      await _storage.write(key: 'refresh', value: refresh);
    }
  }

  Future<void> clear() async {
    _access = null;
    _refresh = null;
    await _storage.deleteAll();
  }

  Future<void> login(String username, String password) async {
    final response = await http.post(Uri.parse('$apiBase/v1/auth/token/'),
        headers: {'Content-Type': 'application/json'}, body: jsonEncode({'username': username, 'password': password}));
    final data = _decode(response);
    if (response.statusCode == 401) throw ApiException(401, 'Wrong username or password.');
    if (response.statusCode >= 400 || data is! Map) throw ApiException(response.statusCode, errorMessage(data, 'Sign-in failed.'), data);
    await _save(data['access'] as String, data['refresh'] as String);
  }

  /// Exchange the refresh token for a new access token (rotating the refresh token).
  Future<bool> refresh() {
    final refresh = _refresh;
    if (refresh == null) return Future.value(false);
    return _refreshing ??= () async {
      try {
        final response = await http.post(Uri.parse('$apiBase/v1/auth/token/refresh/'),
            headers: {'Content-Type': 'application/json'}, body: jsonEncode({'refresh': refresh}));
        if (response.statusCode != 200) return false;
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        await _save(data['access'] as String, data['refresh'] as String?);
        return true;
      } catch (_) {
        return false;
      } finally {
        _refreshing = null;
      }
    }();
  }

  Object? _decode(http.Response r) {
    if (r.bodyBytes.isEmpty) return null;
    try {
      return jsonDecode(utf8.decode(r.bodyBytes));
    } catch (_) {
      return null;
    }
  }

  Future<http.Response> _send(String method, String path, Object? body, {bool retry = true}) async {
    final headers = <String, String>{'X-App-Version': 'android/$appVersion'};
    if (_access != null) headers['Authorization'] = 'Bearer $_access';
    if (body != null) headers['Content-Type'] = 'application/json';
    final request = http.Request(method, Uri.parse('$apiBase$path'))..headers.addAll(headers);
    if (body != null) request.body = jsonEncode(body);
    final response = await http.Response.fromStream(await request.send().timeout(const Duration(seconds: 20)));
    if (response.statusCode == 401 && retry && _refresh != null) {
      if (await refresh()) return _send(method, path, body, retry: false);
      await clear();
      onSignedOut?.call();
    }
    return response;
  }

  Future<dynamic> request(String method, String path, [Object? body]) async {
    final response = await _send(method, path, body);
    final data = _decode(response);
    if (response.statusCode >= 400) {
      throw ApiException(response.statusCode, errorMessage(data, 'Request failed (HTTP ${response.statusCode}).'), data);
    }
    return data;
  }

  Future<dynamic> get(String path) => request('GET', path);
  Future<dynamic> post(String path, [Object? body]) => request('POST', path, body ?? const {});
  Future<dynamic> patch(String path, Object body) => request('PATCH', path, body);
  Future<dynamic> delete(String path) => request('DELETE', path);

  /// Authenticated binary (QR codes, visitor snapshots).
  Future<Uint8List> bytes(String path) async {
    final response = await _send('GET', path, null);
    if (response.statusCode >= 400) throw ApiException(response.statusCode, 'Image not available.');
    return response.bodyBytes;
  }

  /// Results of a paginated list endpoint.
  Future<List<Map<String, dynamic>>> list(String path) async {
    final data = await get(path);
    final results = data is Map ? data['results'] : data;
    return (results as List).cast<Map<String, dynamic>>();
  }
}
