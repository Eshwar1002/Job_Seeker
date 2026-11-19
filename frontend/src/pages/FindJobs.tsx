import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import type { Job, Profile, SearchRun } from '../types';
import JobCard from '../components/JobCard';

const PLATFORMS = [
  { id: 'naukri', label: 'Naukri' },
  { id: 'indeed', label: 'Indeed' },
  { id: 'linkedin', label: 'LinkedIn' },
  { id: 'glassdoor', label: 'Glassdoor' },
  { id: 'company_site', label: 'Company Sites' },
  { id: 'wellfound', label: 'Wellfound' },
  { id: 'hirist', label: 'Hirist' },
];

export default function FindJobs({ refreshKey, onOpenJob, notify, onChanged }: {
  refreshKey: number;
  onOpenJob: (id: number) => void;
  notify: (msg: string, error?: boolean) => void;
  onChanged: () => void;
}) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [run, setRun] = useState<SearchRun | null>(null);
  const [keywords, setKeywords] = useState('');
  const [locations, setLocations] = useState('');
  const [platforms, setPlatforms] = useState<string[]>(PLATFORMS.map((p) => p.id));
  const [hoursOld, setHoursOld] = useState(168);
  const [resultsPerSite, setResultsPerSite] = useState(30);
  const [minScore, setMinScore] = useState(0);
  const [filter, setFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const pollRef = useRef<number | null>(null);

  const loadJobs = useCallback(() => {
    const params = new URLSearchParams({ limit: '200', min_score: String(minScore) });
    if (filter) params.set('q', filter);
    if (sourceFilter) params.set('source', sourceFilter);
    api.listJobs(params).then(setJobs).catch((e) => notify(e.message, true)).finally(() => setLoading(false));
  }, [filter, sourceFilter, minScore, notify]);

  useEffect(() => {
    api.getProfile().then(setProfile).catch(() => {});
    api.listRuns().then((runs) => {
      const active = runs.find((r) => r.status === 'running');
      if (active) setRun(active);
    }).catch(() => {});
  }, []);

  useEffect(() => { loadJobs(); }, [loadJobs, refreshKey]);

  useEffect(() => {
    if (!run || run.status !== 'running') return;
    pollRef.current = window.setInterval(async () => {
      try {
        const r = await api.getRun(run.id);
        setRun(r);
        if (r.status !== 'running') {
          if (pollRef.current) clearInterval(pollRef.current);
          if (r.status === 'completed') {
            const s = r.stats as { new_jobs?: number; ranked?: number };
            notify(`Search done: ${s.ranked ?? 0} matched jobs (${s.new_jobs ?? 0} new)`);
          } else {
            notify(`Search failed: ${r.error}`, true);
          }
          loadJobs();
          onChanged();
        }
      } catch {
        /* keep polling */
      }
    }, 2500);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [run?.id, run?.status, loadJobs, notify, onChanged]);

  const startSearch = async () => {
    try {
      const r = await api.startSearch({
        keywords: keywords ? keywords.split(',').map((k) => k.trim()).filter(Boolean) : null,
        locations: locations ? locations.split(',').map((l) => l.trim()).filter(Boolean) : null,
        platforms,
        hours_old: hoursOld,
        results_per_site: resultsPerSite,
      });
      setRun(r);
      notify('Agents started searching…');
    } catch (e) {
      notify((e as Error).message, true);
    }
  };

  const save = async (id: number) => {
    try {
      await api.saveJob(id);
      notify('Saved to tracker');
      loadJobs();
      onChanged();
    } catch (e) {
      notify((e as Error).message, true);
    }
  };

  const apply = async (job: Job) => {
    window.open(job.url, '_blank', 'noopener');
    try {
      await api.trackJob(job.id, 'applied');
      notify('Marked as applied — good luck!');
      loadJobs();
      onChanged();
    } catch (e) {
      notify((e as Error).message, true);
    }
  };

  const togglePlatform = (id: string) =>
    setPlatforms((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));

  const running = run?.status === 'running';

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-title">Find Jobs</div>
          <div className="page-sub">
            {profile
              ? `${profile.current_role || 'Candidate'} · ${profile.experience_years} yrs · targeting roles up to ~${(profile.experience_years + profile.exp_stretch).toFixed(0)} yrs required`
              : 'Upload your resume on the Profile tab first'}
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 18 }}>
        <div className="search-panel">
          <div className="field" style={{ flex: 2, minWidth: 220 }}>
            <label>Keywords (comma-separated, blank = auto from profile)</label>
            <input placeholder="AI Engineer, Machine Learning Engineer" value={keywords} onChange={(e) => setKeywords(e.target.value)} />
          </div>
          <div className="field" style={{ flex: 1, minWidth: 180 }}>
            <label>Locations (blank = profile prefs)</label>
            <input placeholder="Bengaluru, Pune, Remote" value={locations} onChange={(e) => setLocations(e.target.value)} />
          </div>
          <div className="field">
            <label>Posted within</label>
            <select value={hoursOld} onChange={(e) => setHoursOld(Number(e.target.value))}>
              <option value={24}>24 hours</option>
              <option value={72}>3 days</option>
              <option value={168}>7 days</option>
              <option value={336}>14 days</option>
              <option value={720}>30 days</option>
            </select>
          </div>
          <div className="field">
            <label>Per site</label>
            <select value={resultsPerSite} onChange={(e) => setResultsPerSite(Number(e.target.value))}>
              <option value={15}>15</option>
              <option value={30}>30</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
          </div>
          <button className="btn primary" onClick={startSearch} disabled={running || !profile || platforms.length === 0}>
            {running ? 'Searching…' : 'Run Agents'}
          </button>
        </div>
        <div className="platform-toggles">
          {PLATFORMS.map((p) => (
            <button key={p.id} className={`chip ${platforms.includes(p.id) ? 'on' : ''}`} onClick={() => togglePlatform(p.id)}>
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {run && (
        <div className="run-banner">
          {running && <div className="spinner" />}
          <div style={{ flex: 1 }}>
            <strong>Run #{run.id}</strong> — {running ? run.progress : run.status}
            {!running && run.stats && (
              <span className="muted"> · {String((run.stats as Record<string, unknown>).ranked ?? 0)} matched, {String((run.stats as Record<string, unknown>).new_jobs ?? 0)} new</span>
            )}
            {!running && Array.isArray((run.stats as Record<string, unknown>)?.errors) && ((run.stats as Record<string, unknown>).errors as string[]).length > 0 && (
              <div className="muted" style={{ fontSize: 12 }}>
                Source notes: {((run.stats as Record<string, unknown>).errors as string[]).join(' | ')}
              </div>
            )}
          </div>
          {!running && <button className="btn sm ghost" onClick={() => setRun(null)}>Dismiss</button>}
        </div>
      )}

      <div className="search-panel">
        <div className="field" style={{ flex: 1 }}>
          <label>Filter results</label>
          <input placeholder="Title, company, location…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        </div>
        <div className="field">
          <label>Source</label>
          <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}>
            <option value="">All sources</option>
            {PLATFORMS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
          </select>
        </div>
        <div className="field">
          <label>Min score</label>
          <select value={minScore} onChange={(e) => setMinScore(Number(e.target.value))}>
            <option value={0}>Any</option>
            <option value={40}>40+</option>
            <option value={55}>55+</option>
            <option value={70}>70+</option>
          </select>
        </div>
      </div>

      {loading ? (
        <div className="empty-state"><div className="spinner" style={{ margin: '0 auto' }} /></div>
      ) : jobs.length === 0 ? (
        <div className="empty-state">
          <div className="big">🔎</div>
          <h3>No jobs yet</h3>
          <p>{profile ? 'Hit "Run Agents" to scan Naukri, Indeed, LinkedIn, Glassdoor and company career pages.' : 'Upload your resume on the Profile tab, then run the agents.'}</p>
        </div>
      ) : (
        <div className="jobs-grid">
          {jobs.map((j) => <JobCard key={j.id} job={j} onOpen={onOpenJob} onSave={save} onApply={apply} />)}
        </div>
      )}
    </>
  );
}