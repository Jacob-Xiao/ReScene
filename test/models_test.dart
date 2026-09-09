import 'package:flutter_test/flutter_test.dart';

import 'package:rescene_app/models/membership.dart';
import 'package:rescene_app/models/user.dart';

void main() {
  group('User.fromJson', () {
    test('parses nested membership state', () {
      final user = User.fromJson({
        'id': 7,
        'username': 'alice',
        'role': 'admin',
        'membership': {
          'tier': 'pro',
          'expires_at': '2027-01-01T00:00:00',
          'active': true,
        },
        'created_at': '2026-09-09T10:00:00',
      });

      expect(user.id, 7);
      expect(user.username, 'alice');
      expect(user.isAdmin, isTrue);
      expect(user.membershipTier, 'pro');
      expect(user.membershipActive, isTrue);
      expect(user.membershipExpiresAt, '2027-01-01T00:00:00');
    });

    test('defaults to free/user when fields are missing', () {
      final user = User.fromJson({'id': 1, 'username': 'bob'});

      expect(user.role, 'user');
      expect(user.isAdmin, isFalse);
      expect(user.membershipTier, 'free');
      expect(user.membershipActive, isFalse);
    });
  });

  group('MembershipTier.fromJson', () {
    test('parses catalog entries', () {
      final tier = MembershipTier.fromJson({
        'code': 'pro',
        'name': 'Pro',
        'price': 29,
        'days': 30,
        'features': ['a', 'b'],
      });

      expect(tier.code, 'pro');
      expect(tier.name, 'Pro');
      expect(tier.price, 29.0);
      expect(tier.days, 30);
      expect(tier.features, ['a', 'b']);
      expect(tier.isFree, isFalse);
    });

    test('free tier detection with missing fields', () {
      final tier = MembershipTier.fromJson({});
      expect(tier.isFree, isTrue);
      expect(tier.price, 0.0);
      expect(tier.features, isEmpty);
    });
  });

  group('MembershipOrder.fromJson', () {
    test('parses an order record', () {
      final order = MembershipOrder.fromJson({
        'id': 3,
        'tier': 'studio',
        'price': '99.00',
        'status': 'paid',
        'expires_at': '2026-10-09T00:00:00',
        'created_at': '2026-09-09T00:00:00',
      });

      expect(order.tier, 'studio');
      expect(order.price, 99.0);
      expect(order.status, 'paid');
    });
  });
}
