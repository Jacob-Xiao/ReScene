/** `YYYY-MM-DD` for an ISO timestamp; empty when absent or unparseable. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

/** Same as `formatDate`, but renders `-` for a missing value (profile page). */
export function formatShortDate(iso: string | null | undefined): string {
  if (!iso) return '-';
  const formatted = formatDate(iso);
  return formatted === '' ? '-' : formatted;
}
