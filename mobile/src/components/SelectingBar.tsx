import { MaterialIcons } from '@expo/vector-icons';
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, spacing } from '@/theme';

type IconName = keyof typeof MaterialIcons.glyphMap;

export interface SelectingBarProps {
  title?: string;
  content?: string;
  onPress?: () => void;
  /** Leading icon. */
  iconName?: IconName;
  /** Trailing chevron; defaults to the forward arrow used by the Flutter row. */
  trailingIconName?: IconName;
  isShowArrow?: boolean;
  height?: number;
  testID?: string;
}

/**
 * A settings-style row: optional icon, title, trailing content and arrow.
 *
 * Port of `LlamaSelectingBar` from
 * `lib/models/llama_page/conversation_bar.dart`.
 */
export function SelectingBar({
  title = '',
  content = '',
  onPress,
  iconName,
  trailingIconName = 'arrow-forward-ios',
  isShowArrow = true,
  height = 50,
  testID,
}: SelectingBarProps) {
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [styles.container, { height }, pressed && styles.pressed]}
    >
      {iconName ? <MaterialIcons name={iconName} size={16} color={colors.text} /> : null}
      <Text style={styles.title}>{title}</Text>
      <View style={styles.contentWrap}>
        <Text style={styles.content} numberOfLines={1}>
          {content}
        </Text>
      </View>
      {isShowArrow ? (
        <MaterialIcons name={trailingIconName} size={20} color={colors.text} />
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginHorizontal: spacing.lg,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#EEEEEE',
  },
  pressed: {
    opacity: 0.6,
  },
  title: {
    fontSize: 14,
    color: colors.text,
  },
  contentWrap: {
    flex: 1,
    paddingHorizontal: spacing.lg,
  },
  content: {
    fontSize: 14,
    color: '#CCCCCC',
  },
});
