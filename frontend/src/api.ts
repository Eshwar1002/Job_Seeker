import type { Application, Job, Profile, SearchRun, Stats } from './types';

const BASE = '/api';

async function req<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: options?.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

export const api = {
  getProfile: () => req<Profile | null>('/profile'),
  updateProfile: (body: Partial<Profile>) =>
    req<Profile>('/profile', { method: 'PUT', body: JSON.stringify(body) }),
  uploadResume: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return req<Profile>('/profile/resume', { method: 'POST', body: form });
  },
  startSearch: (body: Record<string, unknown>) =>
    req<SearchRun>('/search', { method: 'POST', body: JSON.stringify(body) }),
  getRun: (id: number) => req<SearchRun>(`/search/runs/${id}`),
  listRuns: () => req<SearchRun[]>('/search/runs'),
  listJobs: (params: URLSearchParams) => req<Job[]>(`/jobs?${params}`),
  getJob: (id: number) => req<Job>(`/jobs/${id}`),
  saveJob: (id: number) => req<Application>(`/jobs/${id}/save`, { method: 'POST' }),
  trackJob: (id: number, status: string) =>
    req<Application>(`/jobs/${id}/track`, { method: 'POST', body: JSON.stringify({ job_id: id, status }) }),
  hideJob: (id: number) => req<{ ok: boolean }>(`/jobs/${id}/hide`, { method: 'POST' }),
  enrichJob: (id: number) => req<Job>(`/jobs/${id}/enrich`, { method: 'POST' }),
  semanticSearch: (q: string) => req<Job[]>(`/jobs/semantic?q=${encodeURIComponent(q)}`),
  listApplications: () => req<Application[]>('/applications'),
  updateApplication: (id: number, body: { status?: string; current_round?: string; notes?: string }) =>
    req<Application>(`/applications/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteApplication: (id: number) => req<{ ok: boolean }>(`/applications/${id}`, { method: 'DELETE' }),
  getStats: () => req<Stats>('/stats'),
  health: () => req<{ status: string; llm_providers: Record<string, { available: boolean; model: string }> }>('/health'),
};