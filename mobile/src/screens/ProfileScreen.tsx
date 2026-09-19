import { MaterialIcons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { useAuth } from '@/auth/AuthContext';
import { formatShortDate } from '@/format';
import { tierMemberLabel } from '@/models/membership';
import { colors, radius, spacing } from '@/theme';

/**
 * Port of `lib/pages/profile_page.dart`: account card, membership summary,
 * admin entry (admins only) and logout.
 */
export default function ProfileScreen() {
  const { user, isAdmin, logout } = useAuth();
  const router = useRouter();

  const tier = user?.membershipTier ?? 'free';
  const initial = user !== null && user.username.length > 0 ? user.username[0].toUpperCase() : '?';

  return (
    <ScrollView style={styles.page} contentContainerStyle={styles.content}>
      <View style={styles.card}>
        <View style={styles.cardRow}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>{initial}</Text>
          </View>
          <View style={styles.identity}>
            <Text style={styles.username}>{user?.username ?? ''}</Text>
            <View style={styles.chipRow}>
              {isAdmin ? <Chip label="Admin" color={colors.warning} background={colors.warningBg} /> : null}
              <Chip label={tierMemberLabel(tier)} color={colors.infoText} background={colors.infoBg} />
            </View>
          </View>
        </View>
      </View>

      <View style={styles.card}>
        <View style={styles.tile}>
          <MaterialIcons name="workspace-premium" size={22} color={colors.textMuted} />
          <View style={styles.tileBody}>
            <Text style={styles.tileTitle}>Membership</Text>
            <Text style={styles.tileSubtitle}>
              {user?.membershipActive
                ? `${tierMemberLabel(tier)} · active until ${formatShortDate(user.membershipExpiresAt)}`
                : 'Free plan'}
            </Text>
          </View>
        </View>
      </View>

      {isAdmin ? (
        <View style={styles.card}>
          <Pressable
            testID="profile-admin-entry"
            accessibilityRole="button"
            onPress={() => router.push('/admin')}
            style={({ pressed }) => [styles.tile, pressed && styles.pressed]}
          >
            <MaterialIcons name="admin-panel-settings" size={22} color={colors.textMuted} />
            <View style={styles.tileBody}>
              <Text style={styles.tileTitle}>Admin console</Text>
              <Text style={styles.tileSubtitle}>Stats, users and request logs</Text>
            </View>
            <MaterialIcons name="chevron-right" size={22} color={colors.textMuted} />
          </Pressable>
        </View>
      ) : null}

      <View style={styles.card}>
        <Pressable
          testID="profile-logout"
          accessibilityRole="button"
          onPress={() => void logout()}
          style={({ pressed }) => [styles.tile, pressed && styles.pressed]}
        >
          <MaterialIcons name="logout" size={22} color={colors.danger} />
          <View style={styles.tileBody}>
            <Text style={[styles.tileTitle, styles.logoutLabel]}>Log out</Text>
          </View>
        </Pressable>
      </View>

      <Text style={styles.footer}>ReScene · local edition</Text>
    </ScrollView>
  );
}

function Chip({ label, color, background }: { label: string; color: string; background: string }) {
  return (
    <View style={[styles.chip, { backgroundColor: background }]}>
      <Text style={[styles.chipText, { color }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.background },
  content: { padding: spacing.lg, paddingBottom: 120, gap: spacing.sm },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.divider,
    overflow: 'hidden',
  },
  cardRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.lg, padding: spacing.xl },
  avatar: {
    width: 60,
    height: 60,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 30,
    backgroundColor: colors.infoBg,
  },
  avatarText: { fontSize: 24, fontWeight: '700', color: colors.primary },
  identity: { flex: 1 },
  username: { fontSize: 22, fontWeight: '700', color: colors.text },
  chipRow: { flexDirection: 'row', gap: 6, marginTop: 6 },
  chip: { paddingHorizontal: spacing.sm, paddingVertical: 3, borderRadius: radius.pill },
  chipText: { fontSize: 11, fontWeight: '600' },
  tile: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.lg,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.lg,
  },
  pressed: { opacity: 0.6 },
  tileBody: { flex: 1 },
  tileTitle: { fontSize: 15, color: colors.text },
  tileSubtitle: { marginTop: 2, fontSize: 13, color: colors.textMuted },
  logoutLabel: { color: colors.danger },
  footer: { marginTop: spacing.lg, textAlign: 'center', fontSize: 12, color: colors.textFaint },
});
