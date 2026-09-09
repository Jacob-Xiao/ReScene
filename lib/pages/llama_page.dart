import 'package:flutter/material.dart';

import '../models/llama_page/conversation_bar.dart';
import 'sub_pages/llama_page_subpages/llama_conversation_page.dart';

class LlamaPage extends StatefulWidget {
  const LlamaPage({super.key});

  @override
  State<LlamaPage> createState() => _LlamaPageState();
}

class _LlamaPageState extends State<LlamaPage> {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: null,
        title: const Text('Llama'),
        automaticallyImplyLeading: false,
      ),
      body: ListView(
        children: <Widget>[
          LlamaSelectingBar(
            iconName: 'Llama',
            title: 'Llama模型',
            content: 'Llama3.2-8B',
            onTap: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (context) => const LlamaConversationPage(),
                ),
              );
            },
            iconButtonName: '>',
          ),
        ],
      ),
    );
  }
}
