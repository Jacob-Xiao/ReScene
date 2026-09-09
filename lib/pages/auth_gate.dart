import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../controllers/auth_controller.dart';
import 'home_page.dart';
import 'login_page.dart';

/// Chooses the login screen or the main shell based on the auth state.
class AuthGate extends StatelessWidget {
  const AuthGate({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<AuthController>(
      builder: (context, auth, _) {
        if (auth.initializing) {
          return const Scaffold(
            body: Center(child: CircularProgressIndicator()),
          );
        }
        return auth.isAuthenticated ? const HomePage() : const LoginPage();
      },
    );
  }
}
