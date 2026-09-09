import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../const.dart';
import '../controllers/auth_controller.dart';
import '../models/membership.dart';
import '../services/api_service.dart';

/// Shows the current membership, the tier catalog and purchase history.
class MembershipPage extends StatefulWidget {
  const MembershipPage({super.key, ApiService? api}) : _api = api;

  final ApiService? _api;

  @override
  State<MembershipPage> createState() => _MembershipPageState();
}

class _MembershipPageState extends State<MembershipPage> {
  late final ApiService _api;
  List<MembershipTier> _tiers = const [];
  List<MembershipOrder> _orders = const [];
  bool _loading = true;
  bool _purchasing = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    final injected = widget._api;
    _api = injected ?? ApiService(baseUrl: ApiConfig.baseUrl);
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    final auth = context.read<AuthController>();
    final tiersResult = await _api.get('/membership/tiers');
    final meResult = await _api.get('/membership/me', token: auth.token);
    if (!mounted) return;

    if (!tiersResult.ok && !meResult.ok) {
      setState(() {
        _loading = false;
        _error = tiersResult.error ?? meResult.error ?? 'Failed to load';
      });
      return;
    }

    setState(() {
      if (tiersResult.ok) {
        _tiers = ((tiersResult.body?['tiers'] as List<dynamic>?) ?? const [])
            .map((e) => MembershipTier.fromJson(e as Map<String, dynamic>))
            .toList();
      }
      if (meResult.ok) {
        _orders = ((meResult.body?['orders'] as List<dynamic>?) ?? const [])
            .map((e) => MembershipOrder.fromJson(e as Map<String, dynamic>))
            .toList();
      }
      _loading = false;
    });
  }

  Future<void> _purchase(MembershipTier tier) async {
    if (_purchasing) return;
    setState(() => _purchasing = true);
    final auth = context.read<AuthController>();
    final result = await _api.post(
      '/membership/purchase',
      body: {'tier': tier.code},
      token: auth.token,
    );
    if (!mounted) return;
    setState(() => _purchasing = false);

    final messenger = ScaffoldMessenger.of(context);
    if (result.ok) {
      await auth.refreshUser();
      await _load();
      messenger.showSnackBar(
        SnackBar(content: Text('${tier.name} activated (demo checkout)')),
      );
    } else {
      messenger.showSnackBar(
        SnackBar(content: Text(result.error ?? 'Purchase failed')),
      );
    }
  }

  String _formatDate(String? iso) {
    if (iso == null) return '';
    final date = DateTime.tryParse(iso);
    if (date == null) return iso;
    return '${date.year}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final user = context.watch<AuthController>().currentUser;
    return Scaffold(
      appBar: AppBar(title: const Text('Membership')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
          ? _ErrorView(message: _error!, onRetry: _load)
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  _CurrentPlanCard(
                    tierName: _tierDisplayName(user?.membershipTier ?? 'free'),
                    expiresAt: user?.membershipExpiresAt,
                    active: user?.membershipActive ?? false,
                    formatDate: _formatDate,
                  ),
                  const SizedBox(height: 16),
                  Text('Plans', style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 8),
                  ..._tiers.map(
                    (tier) => _TierCard(
                      tier: tier,
                      isCurrent: tier.code == (user?.membershipTier ?? 'free'),
                      purchasing: _purchasing,
                      onPurchase: () => _purchase(tier),
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Purchase history',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 8),
                  if (_orders.isEmpty)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 24),
                      child: Center(
                        child: Text(
                          'No purchases yet',
                          style: TextStyle(color: Colors.grey),
                        ),
                      ),
                    )
                  else
                    ..._orders.map(
                      (order) => Card(
                        margin: const EdgeInsets.only(bottom: 8),
                        child: ListTile(
                          leading: const Icon(Icons.receipt_long_outlined),
                          title: Text(_tierDisplayName(order.tier)),
                          subtitle: Text(
                            '${_formatDate(order.createdAt)} · ${order.status}',
                          ),
                          trailing: Text('¥${order.price.toStringAsFixed(0)}'),
                        ),
                      ),
                    ),
                  const SizedBox(height: 24),
                ],
              ),
            ),
    );
  }

  static String _tierDisplayName(String code) {
    switch (code) {
      case 'pro':
        return 'Pro';
      case 'studio':
        return 'Studio';
      default:
        return 'Free';
    }
  }
}

class _CurrentPlanCard extends StatelessWidget {
  const _CurrentPlanCard({
    required this.tierName,
    required this.expiresAt,
    required this.active,
    required this.formatDate,
  });

  final String tierName;
  final String? expiresAt;
  final bool active;
  final String Function(String?) formatDate;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [Color(0xFF3563E9), Color(0xFF7B5CE9)],
        ),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(
                Icons.workspace_premium_outlined,
                color: Colors.white70,
                size: 20,
              ),
              const SizedBox(width: 8),
              Text(
                'Current plan',
                style: TextStyle(color: Colors.white.withValues(alpha: 0.8)),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            tierName,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 28,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            active && expiresAt != null
                ? 'Active until ${formatDate(expiresAt)}'
                : 'Upgrade for priority processing and more',
            style: TextStyle(color: Colors.white.withValues(alpha: 0.85)),
          ),
        ],
      ),
    );
  }
}

class _TierCard extends StatelessWidget {
  const _TierCard({
    required this.tier,
    required this.isCurrent,
    required this.purchasing,
    required this.onPurchase,
  });

  final MembershipTier tier;
  final bool isCurrent;
  final bool purchasing;
  final VoidCallback onPurchase;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    tier.name,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                Text(
                  tier.isFree
                      ? 'Free'
                      : '¥${tier.price.toStringAsFixed(0)} / ${tier.days} days',
                  style: TextStyle(
                    color: Theme.of(context).colorScheme.primary,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            ...tier.features.map(
              (feature) => Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(
                  children: [
                    Icon(
                      Icons.check_circle_outline,
                      size: 16,
                      color: Colors.green.shade600,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        feature,
                        style: const TextStyle(fontSize: 13),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: (isCurrent || tier.isFree || purchasing)
                    ? null
                    : onPurchase,
                child: Text(
                  isCurrent
                      ? 'Current plan'
                      : tier.isFree
                      ? 'Default plan'
                      : 'Upgrade (demo checkout)',
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off, size: 48, color: Colors.grey),
            const SizedBox(height: 12),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            OutlinedButton(onPressed: onRetry, child: const Text('Retry')),
          ],
        ),
      ),
    );
  }
}
