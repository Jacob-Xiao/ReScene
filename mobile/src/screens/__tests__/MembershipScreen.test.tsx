import { fireEvent, waitFor } from '@testing-library/react-native';
import React from 'react';

import MembershipScreen from '@/screens/MembershipScreen';
import { createApi, createFetchMock, jsonResponse, renderWithAuth, userFixture } from '@/testing/helpers';

const TIERS = [
  { code: 'free', name: 'Free', price: 0, days: 0, features: ['YOLO image segmentation'] },
  { code: 'pro', name: 'Pro', price: 29, days: 30, features: ['Priority processing queue'] },
  { code: 'studio', name: 'Studio', price: 99, days: 30, features: ['Batch processing (coming soon)'] },
];

function membershipApi(options: { purchaseStatus?: number } = {}) {
  return createFetchMock((url) => {
    if (url.endsWith('/membership/tiers')) {
      return jsonResponse(200, { success: true, tiers: TIERS });
    }
    if (url.endsWith('/membership/me')) {
      return jsonResponse(200, {
        success: true,
        user: { id: 1, username: 'tester', role: 'user', membership: { tier: 'free', active: false } },
        orders: [
          {
            id: 9,
            tier: 'pro',
            price: 29,
            status: 'paid',
            expires_at: null,
            created_at: '2026-08-01T00:00:00',
          },
        ],
      });
    }
    if (url.endsWith('/membership/purchase')) {
      return options.purchaseStatus === 500
        ? jsonResponse(500, { error: 'Checkout unavailable' })
        : jsonResponse(200, { success: true });
    }
    return jsonResponse(404, {});
  });
}

describe('MembershipScreen', () => {
  it('renders the current plan, the tier catalog and the purchase history', async () => {
    const { fetchImpl } = membershipApi();
    const api = createApi(fetchImpl);

    const { getAllByText, getByText } = await renderWithAuth(<MembershipScreen api={api} />, {
      user: userFixture(1, 'tester'),
      token: 'tok',
      isAuthenticated: true,
    });

    await waitFor(() => expect(getAllByText('Current plan')).toHaveLength(2));
    expect(getAllByText('Free')).toHaveLength(3);
    expect(getByText('Studio')).toBeTruthy();
    expect(getAllByText('Upgrade (demo checkout)')).toHaveLength(2);
    expect(getByText('Purchase history')).toBeTruthy();
    expect(getByText('2026-08-01 · paid')).toBeTruthy();
  });

  it('sends the catalog and history requests with the session token', async () => {
    const { fetchImpl, requests } = membershipApi();
    const api = createApi(fetchImpl);

    const { getAllByText } = await renderWithAuth(<MembershipScreen api={api} />, {
      user: userFixture(1, 'tester'),
      token: 'tok-abc',
      isAuthenticated: true,
    });
    await waitFor(() => expect(getAllByText('Current plan')).toHaveLength(2));

    const tiers = requests.find((request) => request.url.endsWith('/membership/tiers'));
    const me = requests.find((request) => request.url.endsWith('/membership/me'));

    expect(tiers?.init.headers.Authorization).toBeUndefined();
    expect(me?.init.headers.Authorization).toBe('Bearer tok-abc');
  });

  it('surfaces an error with a retry action when the backend is unreachable', async () => {
    const api = createApi(() => Promise.reject(new Error('Network request failed')));

    const { getByText, getByTestId } = await renderWithAuth(<MembershipScreen api={api} />, {
      user: userFixture(1, 'tester'),
      token: 'tok',
      isAuthenticated: true,
    });

    await waitFor(() =>
      expect(getByText('Cannot reach server (Network request failed)')).toBeTruthy(),
    );
    expect(getByTestId('membership-retry')).toBeTruthy();
  });

  it('reports a failed checkout without refreshing the account', async () => {
    const { fetchImpl } = membershipApi({ purchaseStatus: 500 });
    const api = createApi(fetchImpl);
    const refreshUser = jest.fn(async () => undefined);

    const { getAllByText, getByTestId, getByText } = await renderWithAuth(
      <MembershipScreen api={api} />,
      { user: userFixture(1, 'tester'), token: 'tok', isAuthenticated: true, refreshUser },
    );
    await waitFor(() => expect(getAllByText('Upgrade (demo checkout)')).toHaveLength(2));

    await fireEvent.press(getByTestId('membership-buy-pro'));

    await waitFor(() => expect(getByText('Checkout unavailable')).toBeTruthy());
    expect(refreshUser).not.toHaveBeenCalled();
  });
});
