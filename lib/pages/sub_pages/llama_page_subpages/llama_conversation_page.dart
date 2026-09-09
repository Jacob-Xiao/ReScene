import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import '../../../const.dart';

/// Converts the visible conversation history into the `messages` array the
/// Ollama chat API expects, so the model sees the full conversation.
List<Map<String, dynamic>> buildLlamaMessages(
  List<Map<String, String>> history,
) {
  return history
      .where((m) => m['role'] == 'user' || m['role'] == 'assistant')
      .map((m) => {'role': m['role'], 'content': m['content'] ?? ''})
      .toList();
}

class LlamaConversationPage extends StatefulWidget {
  const LlamaConversationPage({super.key});

  @override
  State<LlamaConversationPage> createState() => _LlamaConversationPageState();
}

class _LlamaConversationPageState extends State<LlamaConversationPage> {
  final TextEditingController _adviceController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final List<Map<String, String>> _conversationHistory = []; // 存储对话历史
  bool _isLoading = false;

  @override
  void dispose() {
    _adviceController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _showSnackBar(String message) {
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _sendFeedback() async {
    final advice = _adviceController.text.trim();
    if (advice.isEmpty) {
      _showSnackBar('The input cannot be empty!');
      return;
    }

    setState(() => _isLoading = true);

    // Optimistically show the user message; rolled back if the request fails.
    _conversationHistory.add({
      'role': 'user',
      'content': advice,
      'time': DateTime.now().toString(),
    });
    _scrollToBottom();

    try {
      final response = await http
          .post(
            Uri.parse(ApiConfig.submitContentUrl),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'model': ApiConfig.llamaModel,
              'messages': buildLlamaMessages(_conversationHistory),
              'stream': false,
            }),
          )
          .timeout(ApiConfig.requestTimeout);

      if (!mounted) return;
      setState(() => _isLoading = false);

      if (response.statusCode == 200) {
        final responseData = jsonDecode(response.body);

        String llamaContent = 'No response content received.';
        final apiResponse = responseData['api_response'];
        if (apiResponse is Map &&
            apiResponse['message'] is Map &&
            apiResponse['message']['content'] != null) {
          llamaContent = apiResponse['message']['content'] as String;
        } else if (apiResponse is Map && apiResponse['content'] != null) {
          llamaContent = apiResponse['content'] as String;
        }

        setState(() {
          _conversationHistory.add({
            'role': 'assistant',
            'content': llamaContent,
            'time': DateTime.now().toString(),
          });
        });
        _scrollToBottom();
        _adviceController.clear();
      } else {
        _rollbackUserMessage();
        _showSnackBar('Submission failed. Status: ${response.statusCode}');
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _isLoading = false);
      _rollbackUserMessage();
      _showSnackBar('Network error: $e');
    }
  }

  void _rollbackUserMessage() {
    setState(() {
      if (_conversationHistory.isNotEmpty &&
          _conversationHistory.last['role'] == 'user' &&
          !_hasAssistantReply) {
        _conversationHistory.removeLast();
      }
    });
  }

  bool get _hasAssistantReply =>
      _conversationHistory.any((m) => m['role'] == 'assistant');

  Widget _buildMessageBubble(Map<String, String> message) {
    final bool isUser = message['role'] == 'user';
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 4.0),
      padding: const EdgeInsets.all(12.0),
      decoration: BoxDecoration(
        color: isUser ? Colors.blue.shade50 : Colors.green.shade50,
        borderRadius: BorderRadius.circular(12.0),
        border: Border.all(
          color: isUser ? Colors.blue.shade100 : Colors.green.shade100,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                isUser ? Icons.person : Icons.smart_toy,
                size: 16,
                color: isUser ? Colors.blue : Colors.green,
              ),
              const SizedBox(width: 8),
              Text(
                isUser ? 'You' : 'Llama',
                style: TextStyle(
                  fontWeight: FontWeight.bold,
                  color: isUser ? Colors.blue.shade800 : Colors.green.shade800,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            message['content']!,
            style: const TextStyle(fontSize: 14, height: 1.4),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Llama3.2-8B Chat'),
        backgroundColor: Colors.blue.shade800,
        foregroundColor: Colors.white,
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          children: <Widget>[
            SizedBox(
              height: 60.0,
              child: TextField(
                controller: _adviceController,
                maxLines: null,
                expands: true,
                decoration: InputDecoration(
                  labelText: 'Ask Llama anything...',
                  border: const OutlineInputBorder(),
                  suffixIcon: IconButton(
                    icon: const Icon(Icons.send),
                    onPressed: _isLoading ? null : _sendFeedback,
                    color: _isLoading ? Colors.grey : Colors.blue,
                  ),
                ),
                onSubmitted: _isLoading ? null : (_) => _sendFeedback(),
              ),
            ),
            const SizedBox(height: 20),
            if (_isLoading)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 10),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    CircularProgressIndicator(),
                    SizedBox(width: 10),
                    Text('Llama is thinking...'),
                  ],
                ),
              ),
            const SizedBox(height: 10),
            Expanded(
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.all(16.0),
                decoration: BoxDecoration(
                  border: Border.all(color: Colors.grey.shade300),
                  borderRadius: BorderRadius.circular(12.0),
                  color: Colors.grey.shade50,
                ),
                child: _conversationHistory.isEmpty
                    ? Center(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(
                              Icons.chat_bubble_outline,
                              size: 64,
                              color: Colors.grey.shade400,
                            ),
                            const SizedBox(height: 16),
                            Text(
                              'Start a conversation with Llama!',
                              style: TextStyle(
                                color: Colors.grey,
                                fontSize: 16,
                                fontStyle: FontStyle.italic,
                              ),
                            ),
                          ],
                        ),
                      )
                    : ListView.builder(
                        controller: _scrollController,
                        itemCount: _conversationHistory.length,
                        itemBuilder: (context, index) {
                          return _buildMessageBubble(
                            _conversationHistory[index],
                          );
                        },
                      ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
