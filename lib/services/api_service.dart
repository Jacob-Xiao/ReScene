import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../const.dart';

/// Outcome of one API call: HTTP status plus decoded JSON body (when parseable).
class ApiResult {
  const ApiResult(this.status, this.body);

  final int status;
  final Map<String, dynamic>? body;

  bool get ok => status >= 200 && status < 300;
  String? get error => body?['error'] as String?;
}

/// Thin HTTP wrapper around the local backend.
///
/// The [client] is injectable so widget/unit tests can pass a `MockClient`.
class ApiService {
  ApiService({http.Client? client, String? baseUrl})
    : _client = client ?? http.Client(),
      _baseUrl = baseUrl ?? ApiConfig.baseUrl;

  final http.Client _client;
  final String _baseUrl;

  Map<String, String> _headers(String? token) => {
    'Content-Type': 'application/json',
    if (token != null) 'Authorization': 'Bearer $token',
  };

  Future<ApiResult> get(String path, {String? token}) async {
    try {
      final response = await _client
          .get(Uri.parse('$_baseUrl$path'), headers: _headers(token))
          .timeout(ApiConfig.requestTimeout);
      return ApiResult(response.statusCode, _decode(response.body));
    } on TimeoutException {
      return const ApiResult(0, {'error': 'Request timed out'});
    } on Exception catch (e) {
      return ApiResult(0, {'error': 'Cannot reach server ($e)'});
    }
  }

  Future<ApiResult> post(
    String path, {
    Map<String, dynamic>? body,
    String? token,
  }) async {
    try {
      final response = await _client
          .post(
            Uri.parse('$_baseUrl$path'),
            headers: _headers(token),
            body: body == null ? null : jsonEncode(body),
          )
          .timeout(ApiConfig.requestTimeout);
      return ApiResult(response.statusCode, _decode(response.body));
    } on TimeoutException {
      return const ApiResult(0, {'error': 'Request timed out'});
    } on Exception catch (e) {
      return ApiResult(0, {'error': 'Cannot reach server ($e)'});
    }
  }

  static Map<String, dynamic>? _decode(String body) {
    try {
      final decoded = jsonDecode(body);
      return decoded is Map<String, dynamic> ? decoded : null;
    } on FormatException {
      return null;
    }
  }
}
