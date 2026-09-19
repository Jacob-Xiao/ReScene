import { MaterialIcons } from '@expo/vector-icons';
import type { BottomTabBarProps } from 'expo-router/js-tabs';
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors, spacing } from '@/theme';

type IconName = keyof typeof MaterialIcons.glyphMap;

const TAB_ICONS: Record<string, IconName> = {
  index: 'light',
  llama: 'computer',
  membership: 'card-membership',
  profile: 'person',
};

/**
 * Floating pill tab bar.
 *
 * Replaces `google_nav_bar`'s `GNav` from
 * `lib/components/bottom_nav_bar.dart`: white rounded container inset from the
 * screen edges, active tab gets a filled background and shows its label.
 */
export function BottomNavBar({ state, descriptors, navigation }: BottomTabBarProps) {
  const insets = useSafeAreaInsets();

  return (
    <View style={[styles.bar, { marginBottom: Math.max(insets.bottom, spacing.md) }]}>
      {state.routes.map((route, index) => {
        const focused = state.index === index;
        const options = descriptors[route.key]?.options ?? {};
        const label =
          typeof options.tabBarLabel === 'string' ? options.tabBarLabel : options.title ?? route.name;

        const onPress = () => {
          const event = navigation.emit({
            type: 'tabPress',
            target: route.key,
            canPreventDefault: true,
          });
          if (!focused && !event.defaultPrevented) {
            navigation.navigate(route.name, route.params);
          }
        };

        return (
          <Pressable
            key={route.key}
            testID={`tab-${route.name}`}
            accessibilityRole="tab"
            accessibilityState={{ selected: focused }}
            accessibilityLabel={label}
            onPress={onPress}
            style={[styles.item, focused && styles.itemActive]}
          >
            <MaterialIcons
              name={TAB_ICONS[route.name] ?? 'circle'}
              size={20}
              color={focused ? '#FFFFFF' : colors.primary}
            />
            {focused ? <Text style={styles.label}>{label}</Text> : null}
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: 'row',
    alignSelf: 'center',
    alignItems: 'center',
    gap: 6,
    marginHorizontal: spacing.xl + 1,
    paddingHorizontal: spacing.lg,
    paddingVertical: 10,
    borderRadius: 25,
    backgroundColor: colors.surface,
    // Elevation reads as a shadow on Android and a soft drop shadow on iOS/web.
    elevation: 6,
    shadowColor: '#0F172A',
    shadowOpacity: 0.12,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
  },
  item: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: 15,
  },
  itemActive: {
    backgroundColor: colors.primary,
  },
  label: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '600',
  },
});
