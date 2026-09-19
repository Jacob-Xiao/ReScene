import React from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';

import { colors, radius, spacing } from '@/theme';

export interface PromptTextFieldProps {
  value: string;
  onChangeText: (text: string) => void;
  labelText: string;
  hintText?: string;
  height?: number;
  autoFocus?: boolean;
  maxLength?: number;
  testID?: string;
}

/**
 * Multi-line prompt input with a live character counter.
 *
 * Port of `lib/models/idea_page/prompt_bar.dart`. The Flutter widget listened
 * to a `TextEditingController` to drive the counter; a controlled `value` makes
 * the count derivable, so no listener is needed here.
 */
export function PromptTextField({
  value,
  onChangeText,
  labelText,
  hintText = '',
  height = 60,
  autoFocus = false,
  maxLength,
  testID,
}: PromptTextFieldProps) {
  return (
    <View style={styles.container}>
      <View style={[styles.field, { height }]}>
        <Text style={styles.label}>{labelText}</Text>
        <TextInput
          testID={testID}
          style={styles.input}
          value={value}
          onChangeText={onChangeText}
          placeholder={hintText}
          placeholderTextColor={colors.textFaint}
          multiline
          maxLength={maxLength}
          autoFocus={autoFocus}
          textAlignVertical="top"
        />
      </View>
      {maxLength !== undefined ? (
        <Text style={styles.counter} testID={testID ? `${testID}-counter` : undefined}>
          {`${value.length}/${maxLength}`}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.sm,
  },
  field: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg - 2,
    paddingTop: 6,
  },
  label: {
    fontSize: 11,
    color: colors.textMuted,
  },
  input: {
    flex: 1,
    paddingVertical: 2,
    fontSize: 16,
    color: colors.text,
  },
  counter: {
    alignSelf: 'flex-end',
    marginTop: 2,
    fontSize: 11,
    color: colors.textFaint,
  },
});
