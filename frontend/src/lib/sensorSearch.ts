/** Client-side filter for GAIA devices / ATLAS stations in Alien Monitor. */

export function sensorSearchHaystack(
  ...parts: Array<string | number | boolean | null | undefined>
): string {
  return parts
    .filter((p) => p !== null && p !== undefined && p !== "")
    .map((p) => String(p).toLowerCase())
    .join(" ");
}

/** Every whitespace-separated token must appear somewhere in the haystack. */
export function sensorMatchesQuery(haystack: string, q: string): boolean {
  const needle = q.trim().toLowerCase();
  if (!needle) return true;
  return needle.split(/\s+/).every((tok) => haystack.includes(tok));
}
