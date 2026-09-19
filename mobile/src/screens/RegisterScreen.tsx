import { MaterialIcons } from '@expo/vector-icons';
import React, { useCallback, useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { useAuth } from '@/auth/AuthContext';
import { AppButton } from '@/components/AppButton';
import { Banner } from '@/components/Banner';
import { IconButton } from '@/components/IconButton';
import { colors, radius, spacing } from '@/theme';

const USERNAME_PATTERN = /^[A-Za-z0-9_]{3,32}$/;

interface FieldErrors {
  username?: string;
  password?: string;
  confirm?: string;
}

export function validateRegistration(
  username: string,
  password: string,
  confirm: string,
): FieldErrors {
  const errors: FieldErrors = {};
  if (!USERNAME_PATTERN.test(username.trim())) {
    errors.username = '3-32 letters, digits or underscores';
  }
  if (password.length < 8) {
    errors.password = 'Password must be at least 8 characters';
  }
  if (confirm !== password) {
    errors.confirm = 'Passwords do not match';
  }
  return errors;
}

/**
 * Port of `lib/pages/register_page.dart`.
 *
 * The first registered account becomes the admin (enforced by the backend).
 */
export default function RegisterScreen() {
  const { register } = useAuth();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [obscure, setObscure] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});

  const submit = useCallback(async () => {
    if (busy) return;
    const errors = validateRegistration(username, password, confirm);
    setFieldErrors(errors);
    if (errors.username !== undefined || errors.password !== undefined || errors.confirm !== undefined) {
      return;
    }

    setBusy(true);
    setError(null);
    const message = await register(username.trim(), password);
    setBusy(false);
    if (message !== null) setError(message);
    // On success the `(auth)` guard redirects into the tab shell.
  }, [busy, username, password, confirm, register]);

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        <View style={styles.card}>
          <Text style={styles.title}>Join ReScene</Text>
          <Text style={styles.subtitle}>The first registered account becomes the admin.</Text>

          <Text style={styles.label}>Username</Text>
          <View style={styles.field}>
            <MaterialIcons name="person-outline" size={20} color={colors.textMuted} />
            <TextInput
              testID="register_username"
              style={styles.input}
              value={username}
              onChangeText={setUsername}
              placeholder="Username"
              placeholderTextColor={colors.textFaint}
              autoCapitalize="none"
              autoCorrect={false}
              returnKeyType="next"
            />
          </View>
          {fieldErrors.username ? (
            <Text style={styles.fieldError}>{fieldErrors.username}</Text>
          ) : null}

          <Text style={styles.label}>Password</Text>
          <View style={styles.field}>
            <MaterialIcons name="lock-outline" size={20} color={colors.textMuted} />
            <TextInput
              testID="register_password"
              style={styles.input}
              value={password}
              onChangeText={setPassword}
              placeholder="At least 8 characters"
              placeholderTextColor={colors.textFaint}
              secureTextEntry={obscure}
              autoCapitalize="none"
              autoCorrect={false}
              returnKeyType="next"
            />
            <IconButton
              testID="register_toggle_password"
              icon={obscure ? 'visibility' : 'visibility-off'}
              accessibilityLabel={obscure ? 'Show password' : 'Hide password'}
              size={20}
              onPress={() => setObscure((current) => !current)}
            />
          </View>
          {fieldErrors.password ? (
            <Text style={styles.fieldError}>{fieldErrors.password}</Text>
          ) : null}

          <Text style={styles.label}>Confirm password</Text>
          <View style={styles.field}>
            <MaterialIcons name="lock-outline" size={20} color={colors.textMuted} />
            <TextInput
              testID="register_confirm"
              style={styles.input}
              value={confirm}
              onChangeText={setConfirm}
              placeholder="Repeat password"
              placeholderTextColor={colors.textFaint}
              secureTextEntry={obscure}
              autoCapitalize="none"
              autoCorrect={false}
              returnKeyType="go"
              onSubmitEditing={() => {
                if (!busy) void submit();
              }}
            />
          </View>
          {fieldErrors.confirm ? (
            <Text style={styles.fieldError}>{fieldErrors.confirm}</Text>
          ) : null}

          {error !== null ? (
            <View style={styles.bannerSlot}>
              <Banner message={error} testID="register_error" />
            </View>
          ) : null}

          <AppButton
            testID="register_submit"
            label="Create account"
            onPress={() => void submit()}
            loading={busy}
            style={styles.submit}
          />
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.background },
  scroll: { flexGrow: 1, justifyContent: 'center', padding: spacing.xl },
  card: { width: '100%', maxWidth: 420, alignSelf: 'center' },
  title: { fontSize: 22, fontWeight: '700', color: colors.text },
  subtitle: { marginTop: spacing.xs, marginBottom: spacing.lg, fontSize: 13, color: colors.textMuted },
  label: { marginBottom: 6, fontSize: 12, color: colors.textMuted },
  field: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    minHeight: 52,
    paddingHorizontal: spacing.lg,
    marginBottom: spacing.sm,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
  },
  input: { flex: 1, fontSize: 15, color: colors.text, paddingVertical: spacing.md },
  fieldError: { marginBottom: spacing.sm, marginLeft: spacing.xs, fontSize: 12, color: colors.danger },
  bannerSlot: { marginTop: spacing.sm, marginBottom: spacing.lg },
  submit: { marginTop: spacing.sm },
});
