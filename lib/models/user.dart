/// Account model returned by `/auth/*` and admin endpoints.
class User {
  const User({
    required this.id,
    required this.username,
    required this.role,
    required this.membershipTier,
    this.membershipExpiresAt,
    this.membershipActive = false,
    this.createdAt,
  });

  final int id;
  final String username;
  final String role;
  final String membershipTier;
  final String? membershipExpiresAt;
  final bool membershipActive;
  final String? createdAt;

  bool get isAdmin => role == 'admin';

  factory User.fromJson(Map<String, dynamic> json) {
    final membership = json['membership'] as Map<String, dynamic>?;
    return User(
      id: (json['id'] as num).toInt(),
      username: (json['username'] as String?) ?? '',
      role: (json['role'] as String?) ?? 'user',
      membershipTier: (membership?['tier'] as String?) ?? 'free',
      membershipExpiresAt: membership?['expires_at'] as String?,
      membershipActive: (membership?['active'] as bool?) ?? false,
      createdAt: json['created_at'] as String?,
    );
  }
}
