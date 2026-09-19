import { Redirect, Stack } from 'expo-router';
import React from 'react';

import { useAuth } from '@/auth/AuthContext';
import { Loading } from '@/components/Loading';
import { colors } from '@/theme';

/**
 * Login/register stack.
 *
 * The authenticated redirect is the counterpart of the Flutter `AuthGate`:
 * once `login`/`register` succeeds, this layout swaps the whole stack out for
 * the tab shell, so the screens never navigate themselves.
 */
export default function AuthLayout() {
  const { initializing, isAuthenticated } = useAuth();

  if (initializing) return <Loading />;
  if (isAuthenticated) return <Redirect href="/(tabs)" />;

  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: colors.primary },
        headerTintColor: '#FFFFFF',
        headerTitleStyle: { fontWeight: '600' },
        contentStyle: { backgroundColor: colors.background },
      }}
    >
      <Stack.Screen name="login" options={{ headerShown: false }} />
      <Stack.Screen name="register" options={{ title: 'Create account' }} />
    </Stack>
  );
}
