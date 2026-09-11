import type { User } from './types';
export type { User, Consent, CaseSummary, ChatReply, ResearchPayload, Role } from './types';

export async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const timeout = AbortSignal.timeout(path === '/me' ? 5000 : 15000);
  const response = await fetch('/api' + path, {
    ...options,
    signal: options.signal || timeout,
    credentials: 'same-origin',
    headers: {
      ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...options.headers,
    },
  }).catch(error => {
    throw new Error(error?.name === 'TimeoutError'
      ? 'The service did not respond. Check that both local servers are running.'
      : 'Unable to connect to the service.');
  });
  const data = await response.json().catch(() => ({ detail: 'Unable to reach the service' }));
  if (!response.ok) {
    if (response.status === 401 && path !== '/auth/login' && path !== '/me') {
      window.dispatchEvent(new Event('session-expired'));
    }
    throw new Error(typeof data.detail === 'string' ? data.detail : 'Please check the entered values');
  }
  return data as T;
}

export const post = <T = any>(path: string, body: unknown) =>
  api<T>(path, { method: 'POST', body: JSON.stringify(body) });

export const patch = <T = any>(path: string, body: unknown) =>
  api<T>(path, { method: 'PATCH', body: JSON.stringify(body) });

export function date(value: string) {
  return new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}
