import { fireEvent, waitFor } from '@testing-library/react-native';
import React from 'react';

import LoginScreen from '@/screens/LoginScreen';
import { renderWithAuth } from '@/testing/helpers';

describe('LoginScreen', () => {
  it('shows the brand and the login form when unauthenticated', async () => {
    const { getByText, getByTestId } = await renderWithAuth(<LoginScreen />);

    expect(getByText('ReScene')).toBeTruthy();
    expect(getByText('Segment, restyle and chat — locally.')).toBeTruthy();
    expect(getByText('Log in')).toBeTruthy();
    expect(getByText('Create one')).toBeTruthy();
    expect(getByTestId('login_username')).toBeTruthy();
    expect(getByTestId('login_password')).toBeTruthy();
  });

  it('blocks submission and reports both empty fields', async () => {
    const login = jest.fn(async () => null);
    const { getByTestId, getByText } = await renderWithAuth(<LoginScreen />, { login });

    await fireEvent.press(getByTestId('login_submit'));

    await waitFor(() => expect(getByText('Please enter your username')).toBeTruthy());
    expect(getByText('Please enter your password')).toBeTruthy();
    expect(login).not.toHaveBeenCalled();
  });

  it('submits trimmed credentials and surfaces the server error', async () => {
    const login = jest.fn(async () => 'Incorrect username or password');
    const { getByTestId, getByText } = await renderWithAuth(<LoginScreen />, { login });

    await fireEvent.changeText(getByTestId('login_username'), '  tester  ');
    await fireEvent.changeText(getByTestId('login_password'), 'wrongpass');
    await fireEvent.press(getByTestId('login_submit'));

    await waitFor(() => expect(login).toHaveBeenCalledWith('tester', 'wrongpass'));
    await waitFor(() => expect(getByText('Incorrect username or password')).toBeTruthy());
  });

  it('shows no error banner when login succeeds', async () => {
    const login = jest.fn(async () => null);
    const { getByTestId, queryByTestId } = await renderWithAuth(<LoginScreen />, { login });

    await fireEvent.changeText(getByTestId('login_username'), 'tester');
    await fireEvent.changeText(getByTestId('login_password'), 'password123');
    await fireEvent.press(getByTestId('login_submit'));

    await waitFor(() => expect(login).toHaveBeenCalledTimes(1));
    expect(queryByTestId('login_error')).toBeNull();
  });

  it('toggles password visibility without clearing the field', async () => {
    const { getByTestId } = await renderWithAuth(<LoginScreen />);

    const password = getByTestId('login_password');
    expect(password.props.secureTextEntry).toBe(true);

    await fireEvent.press(getByTestId('login_toggle_password'));

    expect(getByTestId('login_password').props.secureTextEntry).toBe(false);
  });
});
