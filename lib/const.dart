import 'package:flutter/material.dart';

/// App-wide theme values.
final Color? backgroundColor = Colors.brown[300];

/// Configuration for the local backend server (`lib/run/app_DB.py`).
class ApiConfig {
  const ApiConfig._();

  static const String baseUrl = 'http://127.0.0.1:5000';
  static const String yoloSegUrl = '$baseUrl/yolo_seg';
  static const String makeGptUrl = '$baseUrl/makeGPT';
  static const String submitContentUrl = '$baseUrl/submit_content';

  /// Model name sent to Ollama; keep in sync with `ollama pull`.
  static const String llamaModel = 'llama3';

  /// GPT image generation can take a while; YOLO/Ollama are faster.
  static const Duration requestTimeout = Duration(seconds: 120);
  static const Duration gptTimeout = Duration(seconds: 300);
}
