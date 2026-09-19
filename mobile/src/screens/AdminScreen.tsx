import { MaterialIcons } from '@expo/vector-icons';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { ApiService } from '@/api/client';
import { useAuth } from '@/auth/AuthContext';
import { AppButton } from '@/components/AppButton';
import { Banner } from '@/components/Banner';
import { IconButton } from '@/components/IconButton';
import { ApiConfig } from '@/config';
import { asJsonObjectList, type JsonObject } from '@/json';
import { tierDisplayName } from '@/models/membership';
import { isAdmin as isAdminUser, tryUserFromJson, type User } from '@/models/user';
import { colors, radius, spacing } from '@/theme';

type AdminTab = 'stats' | 'users' | 'logs';

/** Membership tiers the backend accepts from the admin console. */
const TIER_CODES = ['free', 'pro', 'studio'] as const;

const TABS: { key: AdminTab; label: string; icon: keyof typeof MaterialIcons.glyphMap }[] = [
  { key: 'stats', label: 'Stats', icon: 'insights' },
  { key: 'users', label: 'Users', icon: 'group' },
  { key: 'logs', label: 'Logs', icon: 'receipt-long' },
];

function parseUsers(value: unknown): User[] {
  return asJsonObjectList(value)
    .map(tryUserFromJson)
    .filter((user): user is User => user !== null);
}

export interface AdminScreenProps {
  api?: ApiService;
}

/**
 * Port of `lib/pages/admin_page.dart`: stats dashboard, user management and
 * request logs.
 *
 * The backend enforces admin-only access; this screen also hides itself from
 * non-admin accounts. The Flutter `TabBar` becomes a segmented control so the
 * port does not need an extra tabs dependency.
 */
export default function AdminScreen({ api }: AdminScreenProps) {
  const apiClient = useMemo(() => api ?? new ApiService(), [api]);
  const { isAdmin } = useAuth();
  const [tab, setTab] = useState<AdminTab>('stats');

  if (!isAdmin) {
    return (
      <View style={styles.centered}>
        <Text style={styles.denied}>Admin access required</Text>
      </View>
    );
  }

  return (
    <View style={styles.page}>
      <View style={styles.segmented}>
        {TABS.map((entry) => {
          const focused = entry.key === tab;
          return (
            <Pressable
              key={entry.key}
              testID={`admin-tab-${entry.key}`}
              accessibilityRole="tab"
              accessibilityState={{ selected: focused }}
              onPress={() => setTab(entry.key)}
              style={[styles.segment, focused && styles.segmentActive]}
            >
              <MaterialIcons
                name={entry.icon}
                size={18}
                color={focused ? '#FFFFFF' : colors.textMuted}
              />
              <Text style={[styles.segmentLabel, focused && styles.segmentLabelActive]}>
                {entry.label}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {tab === 'stats' ? <StatsTab api={apiClient} /> : null}
      {tab === 'users' ? <UsersTab api={apiClient} /> : null}
      {tab === 'logs' ? <LogsTab api={apiClient} /> : null}
    </View>
  );
}

function StatsTab({ api }: { api: ApiService }) {
  const { token } = useAuth();
  const [stats, setStats] = useState<JsonObject>({});
  const [recentUsers, setRecentUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // `loading` starts true and is only cleared here, so the mount effect never
  // synchronously flips state (see MembershipScreen for the same pattern).
  const load = useCallback(async () => {
    const result = await api.get(ApiConfig.adminStatsPath, { token });
    if (!result.ok) {
      setError(result.error ?? `Failed to load stats (HTTP ${result.status})`);
      setLoading(false);
      return;
    }
    setStats(
      result.body?.stats && typeof result.body.stats === 'object'
        ? (result.body.stats as JsonObject)
        : {},
    );
    setRecentUsers(parseUsers(result.body?.recent_users));
    setError(null);
    setLoading(false);
  }, [api, token]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- load() awaits before touching state
    void load();
  }, [load]);

  if (loading) return <Loading />;
  if (error !== null) return <ErrorView message={error} onRetry={() => void load()} />;

  const cards: { label: string; value: string }[] = [
    { label: 'Users', value: String(stats.users ?? 0) },
    { label: 'Paying members', value: String(stats.paying_members ?? 0) },
    { label: 'Orders', value: String(stats.orders ?? 0) },
    { label: 'Revenue', value: `¥${typeof stats.revenue === 'number' ? stats.revenue : 0}` },
    { label: 'GPT requests', value: String(stats.gpt_requests ?? 0) },
    { label: 'YOLO requests', value: String(stats.yolo_requests ?? 0) },
  ];

  return (
    <ScrollView
      style={styles.tabPage}
      contentContainerStyle={styles.tabContent}
      refreshControl={<RefreshControl refreshing={false} onRefresh={() => void load()} />}
    >
      <View style={styles.grid}>
        {cards.map((card) => (
          <View key={card.label} style={styles.statCard} testID={`admin-stat-${card.label}`}>
            <Text style={styles.statLabel}>{card.label}</Text>
            <Text style={styles.statValue}>{card.value}</Text>
          </View>
        ))}
      </View>

      <Text style={styles.sectionTitle}>Recent signups</Text>
      {recentUsers.map((user) => (
        <View key={user.id} style={styles.rowCard}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>{user.username[0]?.toUpperCase() ?? '?'}</Text>
          </View>
          <View style={styles.rowBody}>
            <Text style={styles.rowTitle}>{user.username}</Text>
            <Text style={styles.rowSubtitle}>{user.createdAt?.split('T')[0] ?? ''}</Text>
          </View>
          {isAdminUser(user) ? <Text style={styles.adminBadge}>admin</Text> : null}
        </View>
      ))}
    </ScrollView>
  );
}

function UsersTab({ api }: { api: ApiService }) {
  const { token, user: self } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<User | null>(null);
  const [tierPickerFor, setTierPickerFor] = useState<User | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const load = useCallback(
    async (search: string) => {
      const path =
        search === ''
          ? ApiConfig.adminUsersPath
          : `${ApiConfig.adminUsersPath}?query=${encodeURIComponent(search)}`;
      const result = await api.get(path, { token });
      if (!result.ok) {
        setError(result.error ?? `Failed to load users (HTTP ${result.status})`);
        setLoading(false);
        return;
      }
      setUsers(parseUsers(result.body?.users));
      setError(null);
      setLoading(false);
    },
    [api, token],
  );

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- load() awaits before touching state
    void load('');
  }, [load]);

  const updateUser = useCallback(
    async (target: User, changes: JsonObject) => {
      setSelected(null);
      const result = await api.post(`${ApiConfig.adminUsersPath}/${target.id}`, {
        body: changes,
        token,
      });
      if (!result.ok) {
        setStatus(result.error ?? 'Update failed');
        return;
      }
      setStatus(`${target.username} updated`);
      await load(query.trim());
    },
    [api, token, load, query],
  );

  if (loading) return <Loading />;
  if (error !== null) return <ErrorView message={error} onRetry={() => void load(query.trim())} />;

  return (
    <View style={styles.tabPage}>
      <View style={styles.searchRow}>
        <MaterialIcons name="search" size={20} color={colors.textMuted} />
        <TextInput
          testID="admin-users-search"
          style={styles.searchInput}
          value={query}
          onChangeText={setQuery}
          placeholder="Search username"
          placeholderTextColor={colors.textFaint}
          autoCapitalize="none"
          returnKeyType="search"
          onSubmitEditing={() => void load(query.trim())}
        />
        <IconButton
          testID="admin-users-search-submit"
          icon="arrow-forward"
          accessibilityLabel="Search"
          color={colors.primary}
          onPress={() => void load(query.trim())}
        />
      </View>

      {status !== null ? (
        <View style={styles.statusSlot}>
          <Banner message={status} tone="success" testID="admin-users-status" />
        </View>
      ) : null}

      <ScrollView contentContainerStyle={styles.tabContent}>
        {users.length === 0 ? (
          <Text style={styles.empty}>No users found</Text>
        ) : (
          users.map((user) => (
            <View key={user.id} style={styles.rowCard}>
              <View style={styles.avatar}>
                <Text style={styles.avatarText}>{user.username[0]?.toUpperCase() ?? '?'}</Text>
              </View>
              <View style={styles.rowBody}>
                <Text style={styles.rowTitle}>{user.username}</Text>
                <Text style={styles.rowSubtitle}>
                  {`${isAdminUser(user) ? 'admin' : 'user'} · ${user.membershipTier}`}
                  {user.membershipActive
                    ? ` (to ${user.membershipExpiresAt?.split('T')[0] ?? '-'})`
                    : ''}
                </Text>
              </View>
              <IconButton
                testID={`admin-manage-${user.id}`}
                icon="manage-accounts"
                accessibilityLabel={`Manage ${user.username}`}
                onPress={() => setSelected(user)}
              />
            </View>
          ))
        )}
      </ScrollView>

      <Modal
        visible={selected !== null}
        transparent
        animationType="fade"
        onRequestClose={() => setSelected(null)}
      >
        <Pressable style={styles.modalBackdrop} onPress={() => setSelected(null)}>
          <View style={styles.sheet}>
            <Text style={styles.sheetTitle}>{selected?.username ?? ''}</Text>
            {selected !== null && selected.id !== self?.id ? (
              <SheetAction
                testID="admin-action-role"
                icon={isAdminUser(selected) ? 'shield-moon' : 'shield'}
                label={isAdminUser(selected) ? 'Remove admin' : 'Make admin'}
                onPress={() =>
                  void updateUser(selected, { role: isAdminUser(selected) ? 'user' : 'admin' })
                }
              />
            ) : null}
            <SheetAction
              testID="admin-action-tier"
              icon="workspace-premium"
              label="Set membership"
              detail={`Current: ${selected?.membershipTier ?? ''}`}
              onPress={() => {
                const target = selected;
                setSelected(null);
                setTierPickerFor(target);
              }}
            />
            <SheetAction
              testID="admin-action-extend"
              icon="calendar-month"
              label="Extend +30 days"
              onPress={() => selected !== null && void updateUser(selected, { extend_days: 30 })}
            />
          </View>
        </Pressable>
      </Modal>

      <Modal
        visible={tierPickerFor !== null}
        transparent
        animationType="fade"
        onRequestClose={() => setTierPickerFor(null)}
      >
        <Pressable style={styles.modalBackdrop} onPress={() => setTierPickerFor(null)}>
          <View style={styles.sheet}>
            <Text style={styles.sheetTitle}>Set membership</Text>
            {TIER_CODES.map((code) => (
              <SheetAction
                key={code}
                testID={`admin-tier-${code}`}
                icon="check-circle-outline"
                label={tierDisplayName(code)}
                detail={code}
                onPress={() => {
                  const target = tierPickerFor;
                  setTierPickerFor(null);
                  if (target !== null) void updateUser(target, { tier: code });
                }}
              />
            ))}
          </View>
        </Pressable>
      </Modal>
    </View>
  );
}

function LogsTab({ api }: { api: ApiService }) {
  const { token } = useAuth();
  const [logs, setLogs] = useState<JsonObject[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const result = await api.get(`${ApiConfig.adminLogsPath}?limit=50`, { token });
    if (!result.ok) {
      setError(result.error ?? `Failed to load logs (HTTP ${result.status})`);
      setLoading(false);
      return;
    }
    setLogs(asJsonObjectList(result.body?.logs));
    setError(null);
    setLoading(false);
  }, [api, token]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- load() awaits before touching state
    void load();
  }, [load]);

  if (loading) return <Loading />;
  if (error !== null) return <ErrorView message={error} onRetry={() => void load()} />;
  if (logs.length === 0) return <Text style={styles.empty}>No requests recorded yet</Text>;

  return (
    <ScrollView
      style={styles.tabPage}
      contentContainerStyle={styles.tabContent}
      refreshControl={<RefreshControl refreshing={false} onRefresh={() => void load()} />}
    >
      {logs.map((log, index) => {
        const isGpt = log.kind === 'gpt';
        return (
          <View key={`${String(log.kind)}-${index}`} style={styles.rowCard}>
            <MaterialIcons
              name={isGpt ? 'image' : 'content-cut'}
              size={22}
              color={isGpt ? '#7C3AED' : colors.primary}
            />
            <View style={styles.rowBody}>
              <Text style={styles.rowTitle} numberOfLines={1}>
                {String(log.detail ?? '')}
              </Text>
              <Text style={styles.rowSubtitle}>
                {`${String(log.kind ?? '')} · ${String(log.created_at ?? '').split('T')[0]}`}
              </Text>
            </View>
          </View>
        );
      })}
    </ScrollView>
  );
}

function SheetAction({
  icon,
  label,
  detail,
  onPress,
  testID,
}: {
  icon: keyof typeof MaterialIcons.glyphMap;
  label: string;
  detail?: string;
  onPress: () => void;
  testID: string;
}) {
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [styles.sheetAction, pressed && styles.pressed]}
    >
      <MaterialIcons name={icon} size={22} color={colors.textMuted} />
      <View style={styles.rowBody}>
        <Text style={styles.rowTitle}>{label}</Text>
        {detail !== undefined ? <Text style={styles.rowSubtitle}>{detail}</Text> : null}
      </View>
    </Pressable>
  );
}

function Loading() {
  return (
    <View style={styles.centered}>
      <ActivityIndicator color={colors.primary} />
    </View>
  );
}

function ErrorView({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <View style={styles.centered}>
      <Text style={styles.errorText}>{message}</Text>
      <AppButton label="Retry" variant="outline" onPress={onRetry} testID="admin-retry" />
    </View>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.background },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.md,
    padding: spacing.xl,
    backgroundColor: colors.background,
  },
  denied: { fontSize: 16, color: colors.text },
  errorText: { textAlign: 'center', color: colors.text },
  segmented: {
    flexDirection: 'row',
    gap: spacing.sm,
    padding: spacing.md,
    backgroundColor: colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: colors.divider,
  },
  segment: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 10,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceMuted,
  },
  segmentActive: { backgroundColor: colors.primary },
  segmentLabel: { fontSize: 13, fontWeight: '600', color: colors.textMuted },
  segmentLabelActive: { color: '#FFFFFF' },
  tabPage: { flex: 1 },
  tabContent: { padding: spacing.lg, paddingBottom: 120 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md },
  statCard: {
    flexGrow: 1,
    flexBasis: '45%',
    padding: spacing.lg - 2,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.divider,
  },
  statLabel: { fontSize: 12, color: colors.textMuted },
  statValue: { marginTop: 6, fontSize: 22, fontWeight: '700', color: colors.text },
  sectionTitle: { marginTop: spacing.lg, marginBottom: spacing.sm, fontSize: 16, fontWeight: '600', color: colors.text },
  rowCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    marginBottom: spacing.sm,
    padding: spacing.lg,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.divider,
  },
  avatar: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 18,
    backgroundColor: colors.infoBg,
  },
  avatarText: { fontWeight: '700', color: colors.primary },
  rowBody: { flex: 1 },
  rowTitle: { color: colors.text },
  rowSubtitle: { marginTop: 2, fontSize: 12, color: colors.textMuted },
  adminBadge: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: radius.pill,
    backgroundColor: colors.warningBg,
    color: colors.warning,
    fontSize: 11,
    fontWeight: '600',
    overflow: 'hidden',
  },
  searchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    margin: spacing.lg,
    marginBottom: 0,
    paddingHorizontal: spacing.lg,
    minHeight: 52,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
  },
  searchInput: { flex: 1, fontSize: 15, color: colors.text, paddingVertical: spacing.md },
  statusSlot: { paddingHorizontal: spacing.lg, paddingTop: spacing.md },
  empty: { padding: spacing.xl, textAlign: 'center', color: colors.textMuted },
  modalBackdrop: {
    flex: 1,
    justifyContent: 'flex-end',
    backgroundColor: 'rgba(15, 23, 42, 0.35)',
  },
  sheet: {
    paddingBottom: spacing.xl,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    backgroundColor: colors.surface,
  },
  sheetTitle: {
    padding: spacing.lg,
    fontSize: 16,
    fontWeight: '600',
    color: colors.text,
  },
  sheetAction: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.lg,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  pressed: { opacity: 0.6 },
});
