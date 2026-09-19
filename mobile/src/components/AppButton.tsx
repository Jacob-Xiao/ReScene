import React from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  type StyleProp,
  type ViewStyle,
} from 'react-native';

import { colors, controlHeight, radius } from '@/theme';

export interface AppButtonProps {
  label: string;
  onPress?: () => void;
  disabled?: boolean;
  loading?: boolean;
  variant?: 'primary' | 'outline';
  /** Background override; used by the Idea screen's semantic button colours. */
  backgroundColor?: string;
  testID?: string;
  style?: StyleProp<ViewStyle>;
}

/**
 * Filled/outlined action button.
 *
 * Stands in for the Flutter `ElevatedButton`/`OutlinedButton` theme: same
 * 48pt minimum height and 12pt corner radius.
 */
export function AppButton({
  label,
  onPress,
  disabled = false,
  loading = false,
  variant = 'primary',
  backgroundColor,
  testID,
  style,
}: AppButtonProps) {
  const isDisabled = disabled || loading;
  const isOutline = variant === 'outline';
  const foreground = isOutline ? colors.primary : '#FFFFFF';

  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityState={{ disabled: isDisabled, busy: loading }}
      disabled={isDisabled}
      onPress={onPress}
      style={[
        styles.base,
        isOutline ? styles.outline : { backgroundColor: backgroundColor ?? colors.primary },
        isDisabled && styles.disabled,
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={foreground} />
      ) : (
        <Text style={[styles.label, { color: foreground }]}>{label}</Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    minHeight: controlHeight,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 20,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  outline: {
    backgroundColor: 'transparent',
    borderColor: colors.border,
  },
  disabled: {
    opacity: 0.55,
  },
  label: {
    fontSize: 15,
    fontWeight: '600',
  },
});
