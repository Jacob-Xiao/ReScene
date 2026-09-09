import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/user.dart';
import '../services/api_service.dart';

/// Holds the session state and drives the login gate.
class AuthController extends ChangeNotifier {
  AuthController({ApiService? api}) : _api = api ?? ApiService();

  final ApiService _api;
  static const String _tokenKey = 'rescene_token';

  User? _user;
  String? _token;
  bool initializing = true;

  User? get currentUser => _user;
  String? get token => _token;
  bool get isAuthenticated => _token != null && _user != null;
  bool get isAdmin => _user?.isAdmin ?? false;

  /// Restores a saved session (if any) at app startup.
  Future<void> bootstrap() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final saved = prefs.getString(_tokenKey);
      if (saved != null) {
        _token = saved;
        final result = await _api.get('/auth/me', token: saved);
        if (result.ok && result.body?['user'] != null) {
          _user = User.fromJson(result.body!['user'] as Map<String, dynamic>);
        } else {
          _token = null;
          await _clearToken();
        }
      }
    } on Exception {
      _token = null; // storage unavailable — start unauthenticated
    }
    initializing = false;
    notifyListeners();
  }

  /// Returns an error message on failure, or null on success.
  Future<String?> login(String username, String password) async {
    final result = await _api.post(
      '/auth/login',
      body: {'username': username, 'password': password},
    );
    if (!result.ok) {
      return result.error ?? 'Login failed (HTTP ${result.status})';
    }
    await _applyAuth(result.body!);
    return null;
  }

  /// Returns an error message on failure, or null on success.
  Future<String?> register(String username, String password) async {
    final result = await _api.post(
      '/auth/register',
      body: {'username': username, 'password': password},
    );
    if (!result.ok) {
      return result.error ?? 'Registration failed (HTTP ${result.status})';
    }
    await _applyAuth(result.body!);
    return null;
  }

  /// Re-reads the account (e.g. after a membership purchase).
  Future<void> refreshUser() async {
    if (_token == null) return;
    final result = await _api.get('/auth/me', token: _token);
    if (result.ok && result.body?['user'] != null) {
      _user = User.fromJson(result.body!['user'] as Map<String, dynamic>);
      notifyListeners();
    }
  }

  Future<void> logout() async {
    _token = null;
    _user = null;
    await _clearToken();
    notifyListeners();
  }

  Future<void> _applyAuth(Map<String, dynamic> body) async {
    _token = body['token'] as String?;
    _user = body['user'] is Map<String, dynamic>
        ? User.fromJson(body['user'] as Map<String, dynamic>)
        : null;
    if (_token != null) {
      try {
        final prefs = await SharedPreferences.getInstance();
        await prefs.setString(_tokenKey, _token!);
      } on Exception {
        // Storage unavailable — session just won't survive a restart.
      }
    }
    notifyListeners();
  }

  Future<void> _clearToken() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_tokenKey);
    } on Exception {
      // ignore: storage unavailable
    }
  }

  /// Test hook: set the session directly without touching storage or network.
  @visibleForTesting
  void debugSetSession(User? user, String? token) {
    _user = user;
    _token = token;
    initializing = false;
    notifyListeners();
  }
}
