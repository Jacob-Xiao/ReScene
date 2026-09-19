import { fireEvent, waitFor } from '@testing-library/react-native';
import React from 'react';

import RegisterScreen, { validateRegistration } from '@/screens/RegisterScreen';
import { renderWithAuth } from '@/testing/helpers';

describe('validateRegistration', () => {
  it('accepts a valid username, password and matching confirmation', () => {
    expect(validateRegistration('newuser', 'password123', 'password123')).toEqual({});
  });

  it('rejects usernames outside 3-32 word characters', () => {
    expect(validateRegistration('ab', 'password123', 'password123').username).toBeDefined();
    expect(validateRegistration('a.b', 'password123', 'password123').username).toBeDefined();
    expect(validateRegistration('a'.repeat(33), 'password123', 'password123').username).toBeDefined();
  });

  it('requires at least 8 password characters', () => {
    expect(validateRegistration('newuser', 'short', 'short').password).toBeDefined();
  });

  it('flags a mismatched confirmation', () => {
    expect(validateRegistration('newuser', 'password123', 'different').confirm).toBeDefined();
  });
});

describe('RegisterScreen', () => {
  it('rejects mismatched passwords without calling register', async () => {
    const register = jest.fn(async () => null);
    const { getByTestId, getByText } = await renderWithAuth(<RegisterScreen />, { register });

    await fireEvent.changeText(getByTestId('register_username'), 'newuser');
    await fireEvent.changeText(getByTestId('register_password'), 'password123');
    await fireEvent.changeText(getByTestId('register_confirm'), 'different');
    await fireEvent.press(getByTestId('register_submit'));

    await waitFor(() => expect(getByText('Passwords do not match')).toBeTruthy());
    expect(register).not.toHaveBeenCalled();
  });

  it('rejects a username the backend would refuse', async () => {
    const register = jest.fn(async () => null);
    const { getByTestId, getByText } = await renderWithAuth(<RegisterScreen />, { register });

    await fireEvent.changeText(getByTestId('register_username'), 'a.b');
    await fireEvent.changeText(getByTestId('register_password'), 'password123');
    await fireEvent.changeText(getByTestId('register_confirm'), 'password123');
    await fireEvent.press(getByTestId('register_submit'));

    await waitFor(() => expect(getByText('3-32 letters, digits or underscores')).toBeTruthy());
    expect(register).not.toHaveBeenCalled();
  });

  it('submits trimmed credentials and shows the server error', async () => {
    const register = jest.fn(async () => 'Username already taken');
    const { getByTestId, getByText } = await renderWithAuth(<RegisterScreen />, { register });

    await fireEvent.changeText(getByTestId('register_username'), '  newuser  ');
    await fireEvent.changeText(getByTestId('register_password'), 'password123');
    await fireEvent.changeText(getByTestId('register_confirm'), 'password123');
    await fireEvent.press(getByTestId('register_submit'));

    await waitFor(() => expect(register).toHaveBeenCalledWith('newuser', 'password123'));
    await waitFor(() => expect(getByText('Username already taken')).toBeTruthy());
  });

  it('mentions that the first account becomes the admin', async () => {
    const { getByText } = await renderWithAuth(<RegisterScreen />);

    expect(getByText('Join ReScene')).toBeTruthy();
    expect(getByText('The first registered account becomes the admin.')).toBeTruthy();
  });
});
