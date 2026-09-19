/**
 * App-wide design tokens.
 *
 * Port of `lib/theme.dart`: the same seed blue, surface colours and control
 * metrics the Flutter Material 3 theme uses, expressed as plain values so both
 * StyleSheet objects and the navigation header options can share them.
 */

export const colors = {
  primary: '#3563E9',
  primaryAccent: '#7B5CE9',
  primaryDark: '#1E40AF',

  background: '#F6F8FC',
  surface: '#FFFFFF',
  surfaceMuted: '#F9FAFB',

  border: '#D7DEEB',
  divider: '#E6EAF2',

  text: '#333333',
  textMuted: '#6B7280',
  textFaint: '#9CA3AF',

  danger: '#B91C1C',
  dangerBg: '#FEF2F2',
  dangerBorder: '#FECACA',

  success: '#16A34A',
  warning: '#B45309',
  warningBg: '#FEF3C7',
  infoText: '#1D4ED8',
  infoBg: '#DBEAFE',
} as const;

/** Matches the Flutter `minimumSize: Size.fromHeight(48)` button theme. */
export const controlHeight = 48;

export const radius = {
  sm: 8,
  md: 12,
  lg: 16,
  pill: 999,
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
} as const;
