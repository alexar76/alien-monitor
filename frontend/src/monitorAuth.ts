import { apiUrl } from './api';

export function monitorAuthHeaders(): Record<string, string> {
  // The root monitor token is exchanged once for an HttpOnly SameSite session.
  // This non-secret marker is required on unsafe cookie-authenticated requests.
  return { 'X-Alien-CSRF': '1' };
}

export async function establishMonitorSession(token: string): Promise<boolean> {
  const response = await fetch(apiUrl('/api/auth/session'), {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  });
  return response.ok;
}

export function monitorWsUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const basePath = (import.meta.env.BASE_URL || '/').replace(/\/$/, '');
  return `${protocol}//${window.location.host}${basePath}/ws`;
}
