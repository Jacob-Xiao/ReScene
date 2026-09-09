/// Membership catalog entry returned by `/membership/tiers`.
class MembershipTier {
  const MembershipTier({
    required this.code,
    required this.name,
    required this.price,
    required this.days,
    required this.features,
  });

  final String code;
  final String name;
  final double price;
  final int days;
  final List<String> features;

  bool get isFree => code == 'free';

  factory MembershipTier.fromJson(Map<String, dynamic> json) => MembershipTier(
    code: (json['code'] as String?) ?? 'free',
    name: (json['name'] as String?) ?? '',
    price: (json['price'] as num?)?.toDouble() ?? 0.0,
    days: (json['days'] as num?)?.toInt() ?? 0,
    features: (json['features'] as List<dynamic>? ?? const [])
        .map((e) => e.toString())
        .toList(),
  );
}

/// A recorded purchase from `/membership/me`.
class MembershipOrder {
  const MembershipOrder({
    required this.id,
    required this.tier,
    required this.price,
    required this.status,
    this.expiresAt,
    this.createdAt,
  });

  final int id;
  final String tier;
  final double price;
  final String status;
  final String? expiresAt;
  final String? createdAt;

  factory MembershipOrder.fromJson(Map<String, dynamic> json) =>
      MembershipOrder(
        id: (json['id'] as num).toInt(),
        tier: (json['tier'] as String?) ?? '',
        price: _asDouble(json['price']),
        status: (json['status'] as String?) ?? 'paid',
        expiresAt: json['expires_at'] as String?,
        createdAt: json['created_at'] as String?,
      );

  /// JSON numbers arrive as num; some drivers serialize DECIMAL as string.
  static double _asDouble(Object? value) {
    if (value is num) return value.toDouble();
    if (value is String) return double.tryParse(value) ?? 0.0;
    return 0.0;
  }
}
