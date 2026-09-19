import { MaterialIcons } from '@expo/vector-icons';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';

import { ApiService } from '@/api/client';
import { useAuth } from '@/auth/AuthContext';
import { AppButton } from '@/components/AppButton';
import { Banner } from '@/components/Banner';
import { ApiConfig } from '@/config';
import { formatDate } from '@/format';
import {
  isFreeTier,
  parseOrders,
  parseTiers,
  tierDisplayName,
  type MembershipOrder,
  type MembershipTier,
} from '@/models/membership';
import { colors, radius, spacing } from '@/theme';

export interface MembershipScreenProps {
  api?: ApiService;
}

/**
 * Port of `lib/pages/membership_page.dart`: current plan, tier catalog and
 * purchase history. Checkout is a demo — the backend records the order as paid
 * without contacting a payment gateway.
 */
export default function MembershipScreen({ api }: MembershipScreenProps) {
  const apiClient = useMemo(() => api ?? new ApiService(), [api]);
  const { token, user, refreshUser } = useAuth();

  const [tiers, setTiers] = useState<MembershipTier[]>([]);
  const [orders, setOrders] = useState<MembershipOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [purchasing, setPurchasing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<{ tone: 'success' | 'error'; message: string } | null>(null);

  // `loading` starts true and is only cleared here, so mounting shows a spinner
  // without the effect synchronously flipping state (which would cascade a
  // second render). Pull-to-refresh and retry keep the current content visible.
  const load = useCallback(async () => {
    const [tiersResult, meResult] = await Promise.all([
      apiClient.get(ApiConfig.tiersPath),
      apiClient.get(ApiConfig.membershipMePath, { token }),
    ]);

    if (!tiersResult.ok && !meResult.ok) {
      setError(tiersResult.error ?? meResult.error ?? 'Failed to load');
      setLoading(false);
      return;
    }

    if (tiersResult.ok) setTiers(parseTiers(tiersResult.body?.tiers));
    if (meResult.ok) setOrders(parseOrders(meResult.body?.orders));
    setError(null);
    setLoading(false);
  }, [apiClient, token]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- load() awaits before touching state
    void load();
  }, [load]);

  const purchase = useCallback(
    async (tier: MembershipTier) => {
      if (purchasing) return;
      setPurchasing(true);
      const result = await apiClient.post(ApiConfig.purchasePath, {
        body: { tier: tier.code },
        token,
      });
      setPurchasing(false);

      if (result.ok) {
        await refreshUser();
        await load();
        setStatus({ tone: 'success', message: `${tier.name} activated (demo checkout)` });
      } else {
        setStatus({ tone: 'error', message: result.error ?? 'Purchase failed' });
      }
    },
    [apiClient, token, purchasing, refreshUser, load],
  );

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator color={colors.primary} />
      </View>
    );
  }

  if (error !== null) {
    return (
      <View style={styles.centered}>
        <MaterialIcons name="cloud-off" size={48} color={colors.textFaint} />
        <Text style={styles.errorText}>{error}</Text>
        <AppButton label="Retry" variant="outline" onPress={() => void load()} testID="membership-retry" />
      </View>
    );
  }

  const currentTier = user?.membershipTier ?? 'free';

  return (
    <ScrollView
      style={styles.page}
      contentContainerStyle={styles.content}
      refreshControl={<RefreshControl refreshing={false} onRefresh={() => void load()} />}
    >
      <CurrentPlanCard
        tierName={tierDisplayName(currentTier)}
        expiresAt={user?.membershipExpiresAt ?? null}
        active={user?.membershipActive ?? false}
      />

      {status !== null ? (
        <View style={styles.bannerSlot}>
          <Banner message={status.message} tone={status.tone} testID="membership-status" />
        </View>
      ) : null}

      <Text style={styles.sectionTitle}>Plans</Text>
      {tiers.map((tier) => (
        <TierCard
          key={tier.code}
          tier={tier}
          isCurrent={tier.code === currentTier}
          purchasing={purchasing}
          onPurchase={() => void purchase(tier)}
        />
      ))}

      <Text style={[styles.sectionTitle, styles.historyTitle]}>Purchase history</Text>
      {orders.length === 0 ? (
        <Text style={styles.emptyHistory}>No purchases yet</Text>
      ) : (
        orders.map((order) => (
          <View key={order.id} style={styles.orderCard}>
            <MaterialIcons name="receipt-long" size={22} color={colors.textMuted} />
            <View style={styles.orderBody}>
              <Text style={styles.orderTitle}>{tierDisplayName(order.tier)}</Text>
              <Text style={styles.orderSubtitle}>
                {`${formatDate(order.createdAt)} · ${order.status}`}
              </Text>
            </View>
            <Text style={styles.orderPrice}>{`¥${order.price.toFixed(0)}`}</Text>
          </View>
        ))
      )}
    </ScrollView>
  );
}

function CurrentPlanCard({
  tierName,
  expiresAt,
  active,
}: {
  tierName: string;
  expiresAt: string | null;
  active: boolean;
}) {
  return (
    <View style={styles.planCard}>
      <View style={styles.planHeader}>
        <MaterialIcons name="workspace-premium" size={20} color="rgba(255,255,255,0.8)" />
        <Text style={styles.planLabel}>Current plan</Text>
      </View>
      <Text style={styles.planTier}>{tierName}</Text>
      <Text style={styles.planDetail}>
        {active && expiresAt !== null
          ? `Active until ${formatDate(expiresAt)}`
          : 'Upgrade for priority processing and more'}
      </Text>
    </View>
  );
}

function TierCard({
  tier,
  isCurrent,
  purchasing,
  onPurchase,
}: {
  tier: MembershipTier;
  isCurrent: boolean;
  purchasing: boolean;
  onPurchase: () => void;
}) {
  const free = isFreeTier(tier);
  const label = isCurrent ? 'Current plan' : free ? 'Default plan' : 'Upgrade (demo checkout)';
  return (
    <View style={styles.tierCard}>
      <View style={styles.tierHeader}>
        <Text style={styles.tierName}>{tier.name}</Text>
        <Text style={styles.tierPrice}>
          {free ? 'Free' : `¥${tier.price.toFixed(0)} / ${tier.days} days`}
        </Text>
      </View>
      {tier.features.map((feature) => (
        <View key={feature} style={styles.featureRow}>
          <MaterialIcons name="check-circle-outline" size={16} color={colors.success} />
          <Text style={styles.featureText}>{feature}</Text>
        </View>
      ))}
      <AppButton
        testID={`membership-buy-${tier.code}`}
        label={label}
        onPress={onPurchase}
        disabled={isCurrent || free || purchasing}
        style={styles.tierButton}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.background },
  content: { padding: spacing.lg, paddingBottom: 120 },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.md,
    padding: spacing.xl,
    backgroundColor: colors.background,
  },
  errorText: { textAlign: 'center', color: colors.text },
  planCard: {
    padding: spacing.xl,
    borderRadius: radius.lg,
    backgroundColor: colors.primary,
  },
  planHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  planLabel: { color: 'rgba(255,255,255,0.8)' },
  planTier: { marginTop: spacing.sm, fontSize: 28, fontWeight: '700', color: '#FFFFFF' },
  planDetail: { marginTop: 6, color: 'rgba(255,255,255,0.85)' },
  bannerSlot: { marginTop: spacing.lg },
  sectionTitle: { marginTop: spacing.lg, marginBottom: spacing.sm, fontSize: 16, fontWeight: '600', color: colors.text },
  historyTitle: { marginTop: spacing.md },
  tierCard: {
    marginBottom: spacing.md,
    padding: spacing.lg,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.divider,
  },
  tierHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  tierName: { fontSize: 16, fontWeight: '700', color: colors.text },
  tierPrice: { color: colors.primary, fontWeight: '600' },
  featureRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, paddingVertical: 3 },
  featureText: { flex: 1, fontSize: 13, color: colors.text },
  tierButton: { marginTop: spacing.md },
  emptyHistory: { paddingVertical: spacing.xl, textAlign: 'center', color: colors.textMuted },
  orderCard: {
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
  orderBody: { flex: 1 },
  orderTitle: { color: colors.text },
  orderSubtitle: { marginTop: 2, fontSize: 12, color: colors.textMuted },
  orderPrice: { color: colors.text },
});
