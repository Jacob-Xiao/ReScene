import { MaterialIcons } from '@expo/vector-icons';
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { colors, radius, spacing } from '@/theme';

export type BannerTone = 'error' | 'info' | 'success';

type IconName = keyof typeof MaterialIcons.glyphMap;

const TONES: Record<BannerTone, { background: string; border: string; text: string; icon: IconName }> = {
  error: {
    background: colors.dangerBg,
    border: colors.dangerBorder,
    text: colors.danger,
    icon: 'error-outline',
  },
  info: {
    background: colors.infoBg,
    border: colors.border,
    text: colors.infoText,
    icon: 'info-outline',
  },
  success: {
    background: '#F0FDF4',
    border: '#BBF7D0',
    text: colors.success,
    icon: 'check-circle-outline',
  },
};

export interface BannerProps {
  message: string;
  tone?: BannerTone;
  testID?: string;
}

/**
 * Inline message strip.
 *
 * The Flutter app used `SnackBar` for transient feedback; a persistent inline
 * banner behaves the same way across iOS, Android and web (where `Alert` is a
 * no-op) and is directly assertable in tests.
 */
export function Banner({ message, tone = 'error', testID }: BannerProps) {
  const palette = TONES[tone];
  return (
    <View
      testID={testID}
      accessibilityRole="alert"
      style={[styles.container, { backgroundColor: palette.background, borderColor: palette.border }]}
    >
      <MaterialIcons name={palette.icon} size={20} color={palette.text} />
      <Text style={[styles.message, { color: palette.text }]}>{message}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm + 2,
    paddingHorizontal: 14,
    paddingVertical: spacing.md,
    borderRadius: radius.md - 2,
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
  message: {
    flex: 1,
    fontSize: 13,
  },
});
