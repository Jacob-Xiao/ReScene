/* eslint-disable no-undef */

// AsyncStorage ships no Node implementation; the official in-memory mock keeps
// the default TokenStorage adapter importable under Jest. Tests that need
// deterministic token state inject their own adapter instead.
jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

// expo-router's Link/useRouter need a mounted navigator. Screens are exercised
// standalone here, so the router surface is stubbed; `__mockRouter` is exposed
// so tests can assert navigation calls.
const mockRouter = {
  push: jest.fn(),
  replace: jest.fn(),
  back: jest.fn(),
  navigate: jest.fn(),
};

jest.mock('expo-router', () => {
  const React = require('react');
  const { Text } = require('react-native');
  return {
    __esModule: true,
    useRouter: () => mockRouter,
    Link: ({ children, href, ...rest }) => React.createElement(Text, rest, children),
    Redirect: () => null,
    Stack: Object.assign(() => null, { Screen: () => null }),
    __mockRouter: mockRouter,
  };
});
