/**
 * Narrowing helpers for untrusted JSON.
 *
 * The backend returns `Map<String, dynamic>`-shaped payloads; every field is
 * optional as far as the client is concerned. These helpers keep that
 * "trust nothing, default sensibly" behaviour in one place, matching the
 * `as X? ?? fallback` casts used across the Dart models.
 */

export type JsonObject = Record<string, unknown>;

export function isJsonObject(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Keeps only the object entries of an array (unknown payload shape). */
export function asJsonObjectList(value: unknown): JsonObject[] {
  return Array.isArray(value) ? value.filter(isJsonObject) : [];
}

export function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

export function asNullableString(value: unknown): string | null {
  return typeof value === 'string' ? value : null;
}

export function asBool(value: unknown, fallback = false): boolean {
  return typeof value === 'boolean' ? value : fallback;
}

/** JSON numbers arrive as numbers; some drivers serialize DECIMAL as string. */
export function asDouble(value: unknown): number {
  const parsed = typeof value === 'number' ? value : typeof value === 'string' ? Number(value) : Number.NaN;
  return Number.isFinite(parsed) ? parsed : 0;
}

/**
 * Required numeric field. Mirrors the Dart `(json['id'] as num).toInt()` cast:
 * a missing or non-numeric id is a contract violation, not a default.
 */
export function asRequiredInt(value: unknown, field: string): number {
  const parsed = typeof value === 'number' ? value : typeof value === 'string' ? Number(value) : Number.NaN;
  if (!Number.isFinite(parsed)) {
    throw new TypeError(`Expected a number for "${field}", received ${String(value)}`);
  }
  return Math.trunc(parsed);
}

export function asStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map((entry) => String(entry)) : [];
}
