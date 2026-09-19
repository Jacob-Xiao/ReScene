import { MaterialIcons } from '@expo/vector-icons';
import { Link } from 'expo-router';
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

interface FieldErrors {
  username?: string;
  password?: string;
}

function validate(username: string, password: string): FieldErrors {
  const errors: FieldErrors = {};
  if (username.trim() === '') errors.username = 'Please enter your username';
  if (password === '') errors.password = 'Please enter your password';
  return errors;
}

/**
 * Port of `lib/pages/login_page.dart`.
 *
 * On success the `(auth)` layout guard swaps this screen out for the tab
 * shell — the same behaviour as the Flutter `AuthGate`.
 */
export default function LoginScreen() {
  const { login } = useAuth();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [obscure, setObscure] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});

  const submit = useCallback(async () => {
    if (busy) return;
    const errors = validate(username, password);
    setFieldErrors(errors);
    if (errors.username !== undefined || errors.password !== undefined) return;

    setBusy(true);
    setError(null);
    const message = await login(username.trim(), password);
    setBusy(false);
    if (message !== null) setError(message);
  }, [busy, username, password, login]);

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        <View style={styles.card}>
          <BrandHeader />

          <View style={styles.field}>
            <MaterialIcons name="person-outline" size={20} color={colors.textMuted} />
            <TextInput
              testID="login_username"
              style={styles.input}
              value={username}
              onChangeText={setUsername}
              placeholder="Username"
              placeholderTextColor={colors.textFaint}
              autoCapitalize="none"
              autoCorrect={false}
              textContentType="username"
              returnKeyType="next"
            />
          </View>
          {fieldErrors.username ? (
            <Text style={styles.fieldError}>{fieldErrors.username}</Text>
          ) : null}

          <View style={styles.field}>
            <MaterialIcons name="lock-outline" size={20} color={colors.textMuted} />
            <TextInput
              testID="login_password"
              style={styles.input}
              value={password}
              onChangeText={setPassword}
              placeholder="Password"
              placeholderTextColor={colors.textFaint}
              secureTextEntry={obscure}
              autoCapitalize="none"
              autoCorrect={false}
              textContentType="password"
              returnKeyType="go"
              onSubmitEditing={() => {
                if (!busy) void submit();
              }}
            />
            <IconButton
              testID="login_toggle_password"
              icon={obscure ? 'visibility' : 'visibility-off'}
              accessibilityLabel={obscure ? 'Show password' : 'Hide password'}
              size={20}
              onPress={() => setObscure((current) => !current)}
            />
          </View>
          {fieldErrors.password ? (
            <Text style={styles.fieldError}>{fieldErrors.password}</Text>
          ) : null}

          {error !== null ? (
            <View style={styles.bannerSlot}>
              <Banner message={error} testID="login_error" />
            </View>
          ) : null}

          <AppButton
            testID="login_submit"
            label="Log in"
            onPress={() => void submit()}
            loading={busy}
            style={styles.submit}
          />

          <View style={styles.footer}>
            <Text style={styles.footerText}>No account yet?</Text>
            <Link href="/(auth)/register" testID="login_register_link" style={styles.footerLink}>
              Create one
            </Link>
          </View>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function BrandHeader() {
  return (
    <View style={styles.brand}>
      <View style={styles.logo}>
        <MaterialIcons name="auto-awesome" size={40} color="#FFFFFF" />
      </View>
      <Text style={styles.brandTitle}>ReScene</Text>
      <Text style={styles.brandSubtitle}>Segment, restyle and chat — locally.</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.background },
  scroll: { flexGrow: 1, justifyContent: 'center', padding: spacing.xl },
  card: { width: '100%', maxWidth: 420, alignSelf: 'center' },
  brand: { alignItems: 'center', marginBottom: 28 },
  logo: {
    width: 84,
    height: 84,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 24,
    backgroundColor: colors.primary,
    shadowColor: colors.primary,
    shadowOpacity: 0.35,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: 10 },
    elevation: 8,
  },
  brandTitle: {
    marginTop: 20,
    fontSize: 28,
    fontWeight: '700',
    letterSpacing: 1.2,
    color: colors.text,
  },
  brandSubtitle: { marginTop: 6, color: colors.textMuted },
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
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
    marginTop: spacing.md,
  },
  footerText: { color: colors.textMuted },
  footerLink: { color: colors.primary, fontWeight: '600', paddingHorizontal: spacing.sm },
});
