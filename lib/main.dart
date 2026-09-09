import 'package:flutter/material.dart';
import 'pages/home_page.dart';
import 'pages/sub_pages/llama_page_subpages/llama_conversation_page.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      home: const HomePage(),
      routes: {'/LlamaPage': (context) => const LlamaConversationPage()},
    );
  }
}
