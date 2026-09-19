import {
  isFreeTier,
  membershipOrderFromJson,
  membershipTierFromJson,
  parseTiers,
  tierDisplayName,
  tierMemberLabel,
} from '@/models/membership';
import { buildLlamaMessages, extractLlamaContent } from '@/models/llama';
import { isAdmin, userFromJson } from '@/models/user';

describe('userFromJson', () => {
  it('parses nested membership state', () => {
    const user = userFromJson({
      id: 7,
      username: 'alice',
      role: 'admin',
      membership: {
        tier: 'pro',
        expires_at: '2027-01-01T00:00:00',
        active: true,
      },
      created_at: '2026-09-09T10:00:00',
    });

    expect(user.id).toBe(7);
    expect(user.username).toBe('alice');
    expect(isAdmin(user)).toBe(true);
    expect(user.membershipTier).toBe('pro');
    expect(user.membershipActive).toBe(true);
    expect(user.membershipExpiresAt).toBe('2027-01-01T00:00:00');
  });

  it('defaults to free/user when fields are missing', () => {
    const user = userFromJson({ id: 1, username: 'bob' });

    expect(user.role).toBe('user');
    expect(isAdmin(user)).toBe(false);
    expect(user.membershipTier).toBe('free');
    expect(user.membershipActive).toBe(false);
  });

  it('rejects a payload without a numeric id', () => {
    expect(() => userFromJson({ username: 'ghost' })).toThrow(/user\.id/);
  });
});

describe('membershipTierFromJson', () => {
  it('parses catalog entries', () => {
    const tier = membershipTierFromJson({
      code: 'pro',
      name: 'Pro',
      price: 29,
      days: 30,
      features: ['a', 'b'],
    });

    expect(tier.code).toBe('pro');
    expect(tier.name).toBe('Pro');
    expect(tier.price).toBe(29);
    expect(tier.days).toBe(30);
    expect(tier.features).toEqual(['a', 'b']);
    expect(isFreeTier(tier)).toBe(false);
  });

  it('detects the free tier with missing fields', () => {
    const tier = membershipTierFromJson({});
    expect(isFreeTier(tier)).toBe(true);
    expect(tier.price).toBe(0);
    expect(tier.features).toEqual([]);
  });

  it('parses a tier list and skips non-object entries', () => {
    const tiers = parseTiers([{ code: 'pro', name: 'Pro' }, 'junk', null]);
    expect(tiers).toHaveLength(1);
    expect(tiers[0]?.code).toBe('pro');
  });

  it('maps tier codes to display labels with a Free fallback', () => {
    expect(tierDisplayName('pro')).toBe('Pro');
    expect(tierDisplayName('studio')).toBe('Studio');
    expect(tierDisplayName('unknown')).toBe('Free');
    expect(tierMemberLabel('pro')).toBe('Pro member');
    expect(tierMemberLabel('free')).toBe('Free');
  });
});

describe('membershipOrderFromJson', () => {
  it('parses an order record where DECIMAL arrives as a string', () => {
    const order = membershipOrderFromJson({
      id: 3,
      tier: 'studio',
      price: '99.00',
      status: 'paid',
      expires_at: '2026-10-09T00:00:00',
      created_at: '2026-09-09T00:00:00',
    });

    expect(order.id).toBe(3);
    expect(order.tier).toBe('studio');
    expect(order.price).toBe(99);
    expect(order.status).toBe('paid');
  });

  it('defaults the status to paid', () => {
    expect(membershipOrderFromJson({ id: 1 }).status).toBe('paid');
  });
});

describe('buildLlamaMessages', () => {
  it('maps the full history for the Ollama API', () => {
    const messages = buildLlamaMessages([
      { role: 'user', content: 'hi', time: 't1' },
      { role: 'assistant', content: 'hello!', time: 't2' },
      { role: 'user', content: 'what can you do?', time: 't3' },
    ]);

    expect(messages).toEqual([
      { role: 'user', content: 'hi' },
      { role: 'assistant', content: 'hello!' },
      { role: 'user', content: 'what can you do?' },
    ]);
  });

  it('drops roles the chat API does not accept', () => {
    const messages = buildLlamaMessages([{ role: 'system', content: 'ignore me' }]);
    expect(messages).toEqual([]);
  });
});

describe('extractLlamaContent', () => {
  it('reads the nested Ollama chat shape', () => {
    expect(extractLlamaContent({ api_response: { message: { content: 'hi there' } } })).toBe(
      'hi there',
    );
  });

  it('falls back to a flat content field', () => {
    expect(extractLlamaContent({ api_response: { content: 'flat' } })).toBe('flat');
  });

  it('returns a placeholder when the response is unusable', () => {
    expect(extractLlamaContent(null)).toBe('No response content received.');
    expect(extractLlamaContent({})).toBe('No response content received.');
  });
});
