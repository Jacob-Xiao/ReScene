import { Redirect } from 'expo-router';
import { Tabs } from 'expo-router/js-tabs';
import React from 'react';

import { useAuth } from '@/auth/AuthContext';
import { BottomNavBar } from '@/components/BottomNavBar';
import { Loading } from '@/components/Loading';
import { colors } from '@/theme';

/**
 * Tab shell, replacing `HomePage`'s `IndexedStack` from
 * `lib/pages/home_page.dart`.
 *
 * React Navigation keeps a tab's screen mounted after its first visit, so a
 * picked image or an in-progress chat survives tab switches just like the
 * Flutter `IndexedStack` did.
 */
export default function TabsLayout() {
  const { initializing, isAuthenticated } = useAuth();

  if (initializing) return <Loading />;
  if (!isAuthenticated) return <Redirect href="/(auth)/login" />;

  return (
    <Tabs
      tabBar={(props) => <BottomNavBar {...props} />}
      screenOptions={{
        headerStyle: { backgroundColor: colors.primary },
        headerTintColor: '#FFFFFF',
        headerTitleStyle: { fontWeight: '600' },
      }}
    >
      <Tabs.Screen name="index" options={{ title: 'Idea', tabBarLabel: 'Idea' }} />
      <Tabs.Screen name="llama" options={{ title: 'Llama', tabBarLabel: 'Llama' }} />
      <Tabs.Screen name="membership" options={{ title: 'Membership', tabBarLabel: 'Member' }} />
      <Tabs.Screen name="profile" options={{ title: 'Profile', tabBarLabel: 'Profile' }} />
    </Tabs>
  );
}
