import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../controllers/auth_controller.dart';

class ProfilePage extends StatelessWidget {
  const ProfilePage({super.key});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthController>();
    final user = auth.currentUser;

    return Scaffold(
      appBar: AppBar(title: const Text('Profile')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Row(
                children: [
                  CircleAvatar(
                    radius: 30,
                    backgroundColor: Theme.of(
                      context,
                    ).colorScheme.primary.withValues(alpha: 0.15),
                    child: Text(
                      (user?.username.isNotEmpty ?? false)
                          ? user!.username[0].toUpperCase()
                          : '?',
                      style: TextStyle(
                        fontSize: 24,
                        fontWeight: FontWeight.w700,
                        color: Theme.of(context).colorScheme.primary,
                      ),
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          user?.username ?? '',
                          style: Theme.of(context).textTheme.titleLarge
                              ?.copyWith(fontWeight: FontWeight.w700),
                        ),
                        const SizedBox(height: 6),
                        Row(
                          children: [
                            if (user?.isAdmin ?? false)
                              const _RoleChip(
                                label: 'Admin',
                                color: Color(0xFFB45309),
                                backgroundColor: Color(0xFFFEF3C7),
                              ),
                            const SizedBox(width: 6),
                            _RoleChip(
                              label: _tierLabel(user?.membershipTier ?? 'free'),
                              color: const Color(0xFF1D4ED8),
                              backgroundColor: const Color(0xFFDBEAFE),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 8),
          Card(
            child: Column(
              children: [
                ListTile(
                  leading: const Icon(Icons.workspace_premium_outlined),
                  title: const Text('Membership'),
                  subtitle: Text(
                    (user?.membershipActive ?? false)
                        ? '${_tierLabel(user!.membershipTier)} · active until ${_shortDate(user.membershipExpiresAt)}'
                        : 'Free plan',
                  ),
                ),
              ],
            ),
          ),
          if (auth.isAdmin) ...[
            const SizedBox(height: 8),
            Card(
              child: ListTile(
                leading: const Icon(Icons.admin_panel_settings_outlined),
                title: const Text('Admin console'),
                subtitle: const Text('Stats, users and request logs'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.pushNamed(context, '/admin'),
              ),
            ),
          ],
          const SizedBox(height: 8),
          Card(
            child: ListTile(
              leading: Icon(Icons.logout, color: Colors.red.shade700),
              title: Text(
                'Log out',
                style: TextStyle(color: Colors.red.shade700),
              ),
              onTap: () => auth.logout(),
            ),
          ),
          const SizedBox(height: 16),
          Center(
            child: Text(
              'ReScene · local edition',
              style: TextStyle(color: Colors.grey.shade500, fontSize: 12),
            ),
          ),
        ],
      ),
    );
  }

  static String _tierLabel(String code) {
    switch (code) {
      case 'pro':
        return 'Pro member';
      case 'studio':
        return 'Studio member';
      default:
        return 'Free';
    }
  }

  static String _shortDate(String? iso) {
    final date = iso == null ? null : DateTime.tryParse(iso);
    if (date == null) return '-';
    return '${date.year}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';
  }
}

class _RoleChip extends StatelessWidget {
  const _RoleChip({
    required this.label,
    required this.color,
    required this.backgroundColor,
  });

  final String label;
  final Color color;
  final Color backgroundColor;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: backgroundColor,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontSize: 11,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}
