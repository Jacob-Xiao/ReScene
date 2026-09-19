import { MaterialIcons } from '@expo/vector-icons';
import React from 'react';
import { Pressable, StyleSheet } from 'react-native';

import { colors } from '@/theme';

export interface IconButtonProps {
  icon: keyof typeof MaterialIcons.glyphMap;
  accessibilityLabel: string;
  onPress?: () => void;
  disabled?: boolean;
  color?: string;
  size?: number;
  testID?: string;
}

/**
 * Icon-only action with an expanded touch target.
 *
 * Wrapping the glyph in a `Pressable` (rather than putting `onPress` on the
 * icon's Text) gives a proper hit area on touch devices and a stable node for
 * tests to press.
 */
export function IconButton({
  icon,
  accessibilityLabel,
  onPress,
  disabled = false,
  color = colors.textMuted,
  size = 22,
  testID,
}: IconButtonProps) {
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      hitSlop={8}
      style={({ pressed }) => [styles.base, pressed && styles.pressed]}
    >
      <MaterialIcons name={icon} size={size} color={color} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: { alignItems: 'center', justifyContent: 'center' },
  pressed: { opacity: 0.5 },
});
