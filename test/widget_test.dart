import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:rescene_app/main.dart';
import 'package:rescene_app/models/idea_page/prompt_bar.dart';
import 'package:rescene_app/pages/sub_pages/llama_page_subpages/llama_conversation_page.dart';

void main() {
  // The app targets desktop windows; give tests a realistic desktop surface
  // so fixed-percentage layouts have room.
  void useDesktopSurface(WidgetTester tester) {
    tester.view.physicalSize = const Size(1280, 850);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  }

  testWidgets('App boots to the Idea page with bottom navigation', (
    WidgetTester tester,
  ) async {
    useDesktopSurface(tester);
    await tester.pumpWidget(const MyApp());

    expect(find.text('Idea'), findsWidgets); // nav tab + app bar
    expect(find.text('Segment'), findsOneWidget);
    expect(find.text('Send to GPT'), findsOneWidget);
  });

  testWidgets('Switching tabs preserves page state via IndexedStack', (
    WidgetTester tester,
  ) async {
    useDesktopSurface(tester);
    await tester.pumpWidget(const MyApp());

    await tester.enterText(find.byType(TextField).first, 'hello scene');
    await tester.pump();

    // Switch to the Profile tab (person icon); the Idea page stays mounted.
    // google_nav_bar builds two icon copies for its active/inactive animation.
    await tester.tap(find.byIcon(Icons.person).last);
    await tester.pumpAndSettle();

    expect(find.text('Settings'), findsOneWidget);
    expect(
      find.text('hello scene', skipOffstage: false),
      findsOneWidget,
      reason: 'IndexedStack should keep the Idea page state alive',
    );
  });

  testWidgets('PromptTextField counter updates while typing', (
    WidgetTester tester,
  ) async {
    final controller = TextEditingController();
    addTearDown(controller.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: PromptTextField(
            controller: controller,
            labelText: '输入您的背景需求',
            maxLength: 500,
          ),
        ),
      ),
    );

    expect(find.text('0/500'), findsOneWidget);

    await tester.enterText(find.byType(TextField), 'abc');
    await tester.pump();

    expect(find.text('3/500'), findsOneWidget);
  });

  test('buildLlamaMessages maps the full history for the Ollama API', () {
    final history = <Map<String, String>>[
      {'role': 'user', 'content': 'hi', 'time': 't1'},
      {'role': 'assistant', 'content': 'hello!', 'time': 't2'},
      {'role': 'user', 'content': 'what can you do?', 'time': 't3'},
    ];

    final messages = buildLlamaMessages(history);

    expect(messages, [
      {'role': 'user', 'content': 'hi'},
      {'role': 'assistant', 'content': 'hello!'},
      {'role': 'user', 'content': 'what can you do?'},
    ]);
  });
}
