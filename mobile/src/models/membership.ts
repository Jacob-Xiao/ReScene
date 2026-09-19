import {
  asDouble,
  asJsonObjectList,
  asNullableString,
  asRequiredInt,
  asString,
  asStringList,
  type JsonObject,
} from '@/json';

/** Membership catalog entry returned by `/membership/tiers`. */
export interface MembershipTier {
  code: string;
  name: string;
  price: number;
  days: number;
  features: string[];
}

export function isFreeTier(tier: MembershipTier): boolean {
  return tier.code === 'free';
}

export function membershipTierFromJson(json: JsonObject): MembershipTier {
  return {
    code: asString(json.code, 'free'),
    name: asString(json.name),
    price: asDouble(json.price),
    days: Math.trunc(asDouble(json.days)),
    features: asStringList(json.features),
  };
}

export function parseTiers(value: unknown): MembershipTier[] {
  return asJsonObjectList(value).map(membershipTierFromJson);
}

/** A recorded purchase from `/membership/me`. */
export interface MembershipOrder {
  id: number;
  tier: string;
  price: number;
  status: string;
  expiresAt: string | null;
  createdAt: string | null;
}

export function membershipOrderFromJson(json: JsonObject): MembershipOrder {
  return {
    id: asRequiredInt(json.id, 'order.id'),
    tier: asString(json.tier),
    price: asDouble(json.price),
    status: asString(json.status, 'paid'),
    expiresAt: asNullableString(json.expires_at),
    createdAt: asNullableString(json.created_at),
  };
}

export function parseOrders(value: unknown): MembershipOrder[] {
  return asJsonObjectList(value).map(membershipOrderFromJson);
}

const TIER_LABELS: Record<string, string> = {
  pro: 'Pro',
  studio: 'Studio',
};

/** Display name for a tier code; unknown codes fall back to `Free`. */
export function tierDisplayName(code: string): string {
  return TIER_LABELS[code] ?? 'Free';
}

const TIER_MEMBER_LABELS: Record<string, string> = {
  pro: 'Pro member',
  studio: 'Studio member',
};

/** Profile-page chip label for a tier code. */
export function tierMemberLabel(code: string): string {
  return TIER_MEMBER_LABELS[code] ?? 'Free';
}
