import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';

import '../const.dart';
import '../controllers/auth_controller.dart';
import '../models/user.dart';

/// Admin console: stats dashboard, user management, request logs.
///
/// The backend enforces admin-only access; this page also hides itself from
/// non-admin accounts (no entry point on the profile page).
class AdminPage extends StatefulWidget {
  const AdminPage({super.key, this.apiClient});

  final http.Client? apiClient;

  @override
  State<AdminPage> createState() => _AdminPageState();
}

class _AdminPageState extends State<AdminPage>
    with SingleTickerProviderStateMixin {
  late final TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthController>();
    if (!auth.isAdmin) {
      return Scaffold(
        appBar: AppBar(title: const Text('Admin')),
        body: const Center(child: Text('Admin access required')),
      );
    }
    return Scaffold(
      appBar: AppBar(
        title: const Text('Admin console'),
        bottom: TabBar(
          controller: _tabController,
          labelColor: Colors.white,
          unselectedLabelColor: Colors.white70,
          indicatorColor: Colors.white,
          tabs: const [
            Tab(icon: Icon(Icons.insights_outlined), text: 'Stats'),
            Tab(icon: Icon(Icons.group_outlined), text: 'Users'),
            Tab(icon: Icon(Icons.receipt_long_outlined), text: 'Logs'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          _StatsTab(client: widget.apiClient),
          _UsersTab(client: widget.apiClient),
          _LogsTab(client: widget.apiClient),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Stats

class _StatsTab extends StatefulWidget {
  const _StatsTab({this.client});

  final http.Client? client;

  @override
  State<_StatsTab> createState() => _StatsTabState();
}

class _StatsTabState extends State<_StatsTab>
    with AutomaticKeepAliveClientMixin {
  Map<String, dynamic>? _stats;
  List<dynamic> _recentUsers = const [];
  bool _loading = true;
  String? _error;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    final token = context.read<AuthController>().token ?? '';
    try {
      final response = await (widget.client ?? http.Client())
          .get(
            Uri.parse('${ApiConfig.baseUrl}${ApiConfig.adminStatsPath}'),
            headers: {'Authorization': 'Bearer $token'},
          )
          .timeout(ApiConfig.requestTimeout);
      if (!mounted) return;
      final body = jsonDecode(response.body) as Map<String, dynamic>;
      setState(() {
        _stats = body['stats'] as Map<String, dynamic>?;
        _recentUsers = body['recent_users'] as List<dynamic>? ?? const [];
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = 'Failed to load stats ($e)';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(_error!),
            const SizedBox(height: 12),
            OutlinedButton(onPressed: _load, child: const Text('Retry')),
          ],
        ),
      );
    }
    final stats = _stats ?? const {};
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          GridView.count(
            crossAxisCount: MediaQuery.of(context).size.width > 700 ? 3 : 2,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            mainAxisSpacing: 12,
            crossAxisSpacing: 12,
            childAspectRatio: 1.6,
            children: [
              _StatCard(label: 'Users', value: '${stats['users'] ?? 0}'),
              _StatCard(
                label: 'Paying members',
                value: '${stats['paying_members'] ?? 0}',
              ),
              _StatCard(label: 'Orders', value: '${stats['orders'] ?? 0}'),
              _StatCard(
                label: 'Revenue',
                value: '¥${(stats['revenue'] as num?)?.toDouble() ?? 0}',
              ),
              _StatCard(
                label: 'GPT requests',
                value: '${stats['gpt_requests'] ?? 0}',
              ),
              _StatCard(
                label: 'YOLO requests',
                value: '${stats['yolo_requests'] ?? 0}',
              ),
            ],
          ),
          const SizedBox(height: 16),
          Text(
            'Recent signups',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          ..._recentUsers.map((raw) {
            final user = User.fromJson(raw as Map<String, dynamic>);
            return Card(
              margin: const EdgeInsets.only(bottom: 8),
              child: ListTile(
                leading: CircleAvatar(
                  child: Text(user.username[0].toUpperCase()),
                ),
                title: Text(user.username),
                subtitle: Text(user.createdAt?.split('T').first ?? ''),
                trailing: user.isAdmin
                    ? const Chip(label: Text('admin'))
                    : null,
              ),
            );
          }),
        ],
      ),
    );
  }
}

class _StatCard extends StatelessWidget {
  const _StatCard({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              style: TextStyle(color: Colors.grey.shade600, fontSize: 12),
            ),
            const SizedBox(height: 6),
            Text(
              value,
              style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Users

class _UsersTab extends StatefulWidget {
  const _UsersTab({this.client});

  final http.Client? client;

  @override
  State<_UsersTab> createState() => _UsersTabState();
}

class _UsersTabState extends State<_UsersTab>
    with AutomaticKeepAliveClientMixin {
  final _searchController = TextEditingController();
  List<User> _users = const [];
  bool _loading = true;
  String? _error;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Map<String, String> get _headers {
    final token = context.read<AuthController>().token ?? '';
    return {
      'Authorization': 'Bearer $token',
      'Content-Type': 'application/json',
    };
  }

  Future<void> _load({String? query}) async {
    setState(() {
      _loading = true;
      _error = null;
    });
    final path = query == null || query.isEmpty
        ? ApiConfig.adminUsersPath
        : '${ApiConfig.adminUsersPath}?query=${Uri.encodeQueryComponent(query)}';
    try {
      final response = await (widget.client ?? http.Client())
          .get(Uri.parse('${ApiConfig.baseUrl}$path'), headers: _headers)
          .timeout(ApiConfig.requestTimeout);
      if (!mounted) return;
      final body = jsonDecode(response.body) as Map<String, dynamic>;
      setState(() {
        _users = ((body['users'] as List<dynamic>?) ?? const [])
            .map((e) => User.fromJson(e as Map<String, dynamic>))
            .toList();
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = 'Failed to load users ($e)';
      });
    }
  }

  Future<void> _updateUser(User user, Map<String, dynamic> changes) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      final response = await (widget.client ?? http.Client())
          .post(
            Uri.parse(
              '${ApiConfig.baseUrl}${ApiConfig.adminUsersPath}/${user.id}',
            ),
            headers: _headers,
            body: jsonEncode(changes),
          )
          .timeout(ApiConfig.requestTimeout);
      if (!mounted) return;
      final body = jsonDecode(response.body) as Map<String, dynamic>;
      if (response.statusCode == 200) {
        messenger.showSnackBar(
          SnackBar(content: Text('${user.username} updated')),
        );
        await _load(query: _searchController.text);
      } else {
        messenger.showSnackBar(
          SnackBar(content: Text(body['error'] ?? 'Update failed')),
        );
      }
    } catch (e) {
      messenger.showSnackBar(SnackBar(content: Text('Update failed ($e)')));
    }
  }

  void _showActions(User user) {
    final self = context.read<AuthController>().currentUser;
    showModalBottomSheet<void>(
      context: context,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text(
                user.username,
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ),
            if (user.id != self?.id)
              ListTile(
                leading: Icon(
                  user.isAdmin
                      ? Icons.shield_moon_outlined
                      : Icons.shield_outlined,
                ),
                title: Text(user.isAdmin ? 'Remove admin' : 'Make admin'),
                onTap: () {
                  Navigator.pop(context);
                  _updateUser(user, {'role': user.isAdmin ? 'user' : 'admin'});
                },
              ),
            ListTile(
              leading: const Icon(Icons.workspace_premium_outlined),
              title: const Text('Set membership'),
              subtitle: Text('Current: ${user.membershipTier}'),
              onTap: () {
                Navigator.pop(context);
                _showTierPicker(user);
              },
            ),
            ListTile(
              leading: const Icon(Icons.calendar_month_outlined),
              title: const Text('Extend +30 days'),
              onTap: () {
                Navigator.pop(context);
                _updateUser(user, {'extend_days': 30});
              },
            ),
          ],
        ),
      ),
    );
  }

  void _showTierPicker(User user) {
    showModalBottomSheet<void>(
      context: context,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text('Set membership'),
            ),
            for (final code in const ['free', 'pro', 'studio'])
              ListTile(
                leading: const Icon(Icons.check_circle_outline),
                title: Text(code),
                onTap: () {
                  Navigator.pop(context);
                  _updateUser(user, {'tier': code});
                },
              ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(_error!),
            const SizedBox(height: 12),
            OutlinedButton(onPressed: _load, child: const Text('Retry')),
          ],
        ),
      );
    }
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(16),
          child: TextField(
            controller: _searchController,
            decoration: InputDecoration(
              labelText: 'Search username',
              prefixIcon: const Icon(Icons.search),
              suffixIcon: IconButton(
                icon: const Icon(Icons.arrow_forward),
                onPressed: () => _load(query: _searchController.text),
              ),
            ),
            onSubmitted: (value) => _load(query: value),
          ),
        ),
        Expanded(
          child: RefreshIndicator(
            onRefresh: _load,
            child: _users.isEmpty
                ? const Center(child: Text('No users found'))
                : ListView.builder(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    itemCount: _users.length,
                    itemBuilder: (context, index) {
                      final user = _users[index];
                      return Card(
                        margin: const EdgeInsets.only(bottom: 8),
                        child: ListTile(
                          leading: CircleAvatar(
                            child: Text(user.username[0].toUpperCase()),
                          ),
                          title: Text(user.username),
                          subtitle: Text(
                            '${user.isAdmin ? 'admin' : 'user'} · ${user.membershipTier}'
                            '${user.membershipActive ? ' (to ${user.membershipExpiresAt?.split('T').first ?? '-'})' : ''}',
                          ),
                          trailing: IconButton(
                            icon: const Icon(Icons.manage_accounts_outlined),
                            onPressed: () => _showActions(user),
                          ),
                        ),
                      );
                    },
                  ),
          ),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Logs

class _LogsTab extends StatefulWidget {
  const _LogsTab({this.client});

  final http.Client? client;

  @override
  State<_LogsTab> createState() => _LogsTabState();
}

class _LogsTabState extends State<_LogsTab> with AutomaticKeepAliveClientMixin {
  List<Map<String, dynamic>> _logs = const [];
  bool _loading = true;
  String? _error;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    final token = context.read<AuthController>().token ?? '';
    try {
      final response = await (widget.client ?? http.Client())
          .get(
            Uri.parse(
              '${ApiConfig.baseUrl}${ApiConfig.adminLogsPath}?limit=50',
            ),
            headers: {'Authorization': 'Bearer $token'},
          )
          .timeout(ApiConfig.requestTimeout);
      if (!mounted) return;
      final body = jsonDecode(response.body) as Map<String, dynamic>;
      setState(() {
        _logs = ((body['logs'] as List<dynamic>?) ?? const [])
            .map((e) => e as Map<String, dynamic>)
            .toList();
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = 'Failed to load logs ($e)';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(_error!),
            const SizedBox(height: 12),
            OutlinedButton(onPressed: _load, child: const Text('Retry')),
          ],
        ),
      );
    }
    if (_logs.isEmpty) {
      return const Center(child: Text('No requests recorded yet'));
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.builder(
        padding: const EdgeInsets.all(16),
        itemCount: _logs.length,
        itemBuilder: (context, index) {
          final log = _logs[index];
          final isGpt = log['kind'] == 'gpt';
          return Card(
            margin: const EdgeInsets.only(bottom: 8),
            child: ListTile(
              leading: Icon(
                isGpt ? Icons.image_outlined : Icons.content_cut,
                color: isGpt ? Colors.deepPurple : Colors.blue,
              ),
              title: Text(
                (log['detail'] ?? '').toString(),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              subtitle: Text(
                '${log['kind']} · ${log['created_at']?.toString().split('T').first ?? ''}',
              ),
            ),
          );
        },
      ),
    );
  }
}
