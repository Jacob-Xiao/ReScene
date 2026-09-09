import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'controllers/auth_controller.dart';
import 'pages/admin_page.dart';
import 'pages/auth_gate.dart';
import 'pages/register_page.dart';
import 'theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  final authController = AuthController();
  authController.bootstrap();
  runApp(ReSceneApp(authController: authController));
}

class ReSceneApp extends StatelessWidget {
  const ReSceneApp({super.key, required this.authController});

  final AuthController authController;

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider<AuthController>.value(
      value: authController,
      child: MaterialApp(
        title: 'ReScene',
        debugShowCheckedModeBanner: false,
        theme: appTheme,
        home: const AuthGate(),
        routes: {
          '/register': (context) => const RegisterPage(),
          '/admin': (context) => const AdminPage(),
        },
      ),
    );
  }
}
