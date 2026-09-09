import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:rescene_app/controllers/auth_controller.dart';
import 'package:rescene_app/models/idea_page/prompt_bar.dart';
import 'package:rescene_app/models/user.dart';
import 'package:rescene_app/pages/auth_gate.dart';
import 'package:rescene_app/pages/home_page.dart';
import 'package:rescene_app/pages/login_page.dart';
import 'package:rescene_app/pages/membership_page.dart';
import 'package:rescene_app/pages/register_page.dart';
import 'package:rescene_app/pages/sub_pages/llama_page_subpages/llama_conversation_page.dart';
import 'package:rescene_app/services/api_service.dart';

Map<String, dynamic> _userJson(
  int id,
  String name, {
  String role = 'user',
  String tier = 'free',
  bool active = false,
}) => {
  'id': id,
  'username': name,
  'role': role,
  'membership': {
    'tier': tier,
    'expires_at': active ? '2027-01-01T00:00:00' : null,
    'active': active,
  },
  'created_at': '2026-09-09T10:00:00',
};

http.Client _mockClient(http.Response Function(http.Request) handler) =>
    MockClient((request) async => handler(request));

AuthController _authedController({String role = 'user'}) {
  final controller = AuthController(
    api: ApiService(
      client: _mockClient(
        (request) => http.Response(
          jsonEncode({
            'success': true,
            'user': _userJson(1, 'tester', role: role),
          }),
          200,
        ),
      ),
    ),
  );
  controller.debugSetSession(
    User.fromJson(_userJson(1, 'tester', role: role)),
    'test-token',
  );
  return controller;
}

Widget _wrap(AuthController controller, Widget child) =>
    ChangeNotifierProvider<AuthController>.value(
      value: controller,
      child: MaterialApp(home: child),
    );

// The app targets desktop windows; give tests a realistic desktop surface
// so fixed-percentage layouts have room.
void useDesktopSurface(WidgetTester tester) {
  tester.view.physicalSize = const Size(1280, 850);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  testWidgets('Login page shows when unauthenticated', (tester) async {
    final controller = AuthController(
      api: ApiService(
        client: _mockClient((request) => http.Response('{}', 404)),
      ),
    );
    controller.debugSetSession(null, null);

    await tester.pumpWidget(_wrap(controller, const AuthGate()));

    expect(find.text('ReScene'), findsOneWidget);
    expect(find.text('Log in'), findsOneWidget);
    expect(find.text('Create one'), findsOneWidget);
  });

  testWidgets('Auth gate shows the main tabs when authenticated', (
    tester,
  ) async {
    useDesktopSurface(tester);
    final controller = _authedController();

    await tester.pumpWidget(_wrap(controller, const AuthGate()));

    expect(find.text('Segment'), findsOneWidget);
    expect(find.text('Send to GPT'), findsOneWidget);
    expect(find.text('Member'), findsOneWidget);
    expect(find.text('Profile'), findsWidgets);
  });

  testWidgets('Switching tabs preserves page state via IndexedStack', (
    tester,
  ) async {
    useDesktopSurface(tester);
    final controller = _authedController();

    await tester.pumpWidget(_wrap(controller, const HomePage()));

    await tester.enterText(find.byType(TextField).first, 'hello scene');
    await tester.pump();

    // Switch to the Profile tab (person icon); the Idea page stays mounted.
    // google_nav_bar builds two icon copies for its active/inactive animation.
    await tester.tap(find.byIcon(Icons.person).last);
    await tester.pumpAndSettle();

    expect(find.text('Log out'), findsOneWidget);
    expect(
      find.text('hello scene', skipOffstage: false),
      findsOneWidget,
      reason: 'IndexedStack should keep the Idea page state alive',
    );
  });

  testWidgets('Login submits credentials and stores the session', (
    tester,
  ) async {
    http.Request? captured;
    final client = _mockClient((request) {
      captured = request;
      return http.Response(
        jsonEncode({
          'success': true,
          'token': 'tok-123',
          'user': _userJson(1, 'tester'),
        }),
        200,
      );
    });
    final controller = AuthController(api: ApiService(client: client));

    await tester.pumpWidget(_wrap(controller, const LoginPage()));

    await tester.enterText(find.byKey(const Key('login_username')), 'tester');
    await tester.enterText(
      find.byKey(const Key('login_password')),
      'password123',
    );
    await tester.tap(find.byKey(const Key('login_submit')));
    await tester.pumpAndSettle();

    expect(controller.isAuthenticated, isTrue);
    expect(controller.currentUser?.username, 'tester');
    expect(captured?.url.path, '/auth/login');
    expect(captured?.headers.containsKey('Authorization'), isFalse);
  });

  testWidgets('Login failure shows the server error', (tester) async {
    final client = _mockClient(
      (request) => http.Response(
        jsonEncode({
          'success': false,
          'error': 'Incorrect username or password',
        }),
        401,
      ),
    );
    final controller = AuthController(api: ApiService(client: client));

    await tester.pumpWidget(_wrap(controller, const LoginPage()));

    await tester.enterText(find.byKey(const Key('login_username')), 'tester');
    await tester.enterText(
      find.byKey(const Key('login_password')),
      'wrongpass',
    );
    await tester.tap(find.byKey(const Key('login_submit')));
    await tester.pumpAndSettle();

    expect(controller.isAuthenticated, isFalse);
    expect(find.text('Incorrect username or password'), findsOneWidget);
  });

  testWidgets('Register rejects mismatched passwords', (tester) async {
    final controller = AuthController(
      api: ApiService(
        client: _mockClient((request) => http.Response('{}', 500)),
      ),
    );

    await tester.pumpWidget(_wrap(controller, const RegisterPage()));

    await tester.enterText(
      find.byKey(const Key('register_username')),
      'newuser',
    );
    await tester.enterText(
      find.byKey(const Key('register_password')),
      'password123',
    );
    await tester.enterText(
      find.byKey(const Key('register_confirm')),
      'different',
    );
    await tester.tap(find.byKey(const Key('register_submit')));
    await tester.pump();

    expect(find.text('Passwords do not match'), findsOneWidget);
    expect(controller.isAuthenticated, isFalse);
  });

  testWidgets('Membership page renders tiers and history from the API', (
    tester,
  ) async {
    useDesktopSurface(tester);
    final api = ApiService(
      client: _mockClient((request) {
        if (request.url.path == '/membership/tiers') {
          return http.Response(
            jsonEncode({
              'success': true,
              'tiers': [
                {
                  'code': 'free',
                  'name': 'Free',
                  'price': 0,
                  'days': 0,
                  'features': ['YOLO image segmentation'],
                },
                {
                  'code': 'pro',
                  'name': 'Pro',
                  'price': 29,
                  'days': 30,
                  'features': ['Priority processing queue'],
                },
                {
                  'code': 'studio',
                  'name': 'Studio',
                  'price': 99,
                  'days': 30,
                  'features': ['Batch processing (coming soon)'],
                },
              ],
            }),
            200,
          );
        }
        if (request.url.path == '/membership/me') {
          return http.Response(
            jsonEncode({
              'success': true,
              'user': _userJson(1, 'tester', tier: 'free', active: false),
              'orders': [
                {
                  'id': 9,
                  'tier': 'pro',
                  'price': 29,
                  'status': 'paid',
                  'expires_at': null,
                  'created_at': '2026-08-01T00:00:00',
                },
              ],
            }),
            200,
          );
        }
        return http.Response('{}', 404);
      }),
    );

    final controller = _authedController();
    await tester.pumpWidget(_wrap(controller, MembershipPage(api: api)));
    await tester.pumpAndSettle();

    expect(
      find.text('Current plan'),
      findsNWidgets(2),
    ); // plan card + Free tier button
    // 'Free': plan card + tier title + tier price label.
    expect(find.text('Free'), findsNWidgets(3));
    expect(find.text('Studio'), findsOneWidget);
    expect(find.text('Upgrade (demo checkout)'), findsNWidgets(2));

    // The history list is lazy; scroll the order into view before asserting.
    await tester.scrollUntilVisible(
      find.textContaining('2026-08-01'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    // 'Pro' now counts the tier card plus the purchase-history entry.
    expect(find.text('Pro'), findsNWidgets(2));
    expect(find.text('Purchase history'), findsOneWidget);
  });

  testWidgets('PromptTextField counter updates while typing', (tester) async {
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
