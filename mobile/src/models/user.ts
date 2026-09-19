import {
  asBool,
  asNullableString,
  asRequiredInt,
  asString,
  isJsonObject,
  type JsonObject,
} from '@/json';

/** Account model returned by `/auth/*` and admin endpoints. */
export interface User {
  id: number;
  username: string;
  role: string;
  membershipTier: string;
  membershipExpiresAt: string | null;
  membershipActive: boolean;
  createdAt: string | null;
}

export function isAdmin(user: User | null | undefined): boolean {
  return user?.role === 'admin';
}

export function userFromJson(json: JsonObject): User {
  const membership = isJsonObject(json.membership) ? json.membership : null;
  return {
    id: asRequiredInt(json.id, 'user.id'),
    username: asString(json.username),
    role: asString(json.role, 'user'),
    membershipTier: asString(membership?.tier, 'free'),
    membershipExpiresAt: asNullableString(membership?.expires_at),
    membershipActive: asBool(membership?.active),
    createdAt: asNullableString(json.created_at),
  };
}

/** `userFromJson` that yields null instead of throwing on a corrupt payload. */
export function tryUserFromJson(json: unknown): User | null {
  if (!isJsonObject(json)) return null;
  try {
    return userFromJson(json);
  } catch {
    return null;
  }
}
