/** Bearer token for protected monitor API routes (set at build via VITE_ALIEN_API_TOKEN). */
export function monitorAuthHeaders(): Record<string, string> {
  const token = String(import.meta.env.VITE_ALIEN_API_TOKEN || '').trim();
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}
