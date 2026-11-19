import { useCallback, useEffect, useState } from 'react';
import { api } from './api';
import Dashboard from './pages/Dashboard';
import FindJobs from './pages/FindJobs';
import Tracker from './pages/Tracker';
import ProfilePage from './pages/Profile';
import JobDetail from './components/JobDetail';

type Tab = 'dashboard' | 'find' | 'tracker' | 'profile';

const TABS: { id: Tab; label: string }[] = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'find', label: 'Find Jobs' },
  { id: 'tracker', label: 'Tracker' },
  { id: 'profile', label: 'Profile' },
];

export default function App() {
  const [tab, setTab] = useState<Tab>('dashboard');
  const [toast, setToast] = useState<{ msg: string; error?: boolean } | null>(null);
  const [selectedJob, setSelectedJob] = useState<number | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [providers, setProviders] = useState<Record<string, { available: boolean; model: string }>>({});

  const notify = useCallback((msg: string, error = false) => {
    setToast({ msg, error });
    setTimeout(() => setToast(null), 3500);
  }, []);

  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);

  useEffect(() => {
    api.health().then((h) => setProviders(h.llm_providers)).catch(() => {});
    api.getProfile().then((p) => {
      if (!p) setTab('profile');
    }).catch(() => {});
  }, []);

  const anyLLM = Object.values(providers).some((p) => p.available);

  return (
    <>
      <header className="topbar">
        <div className="logo">
          <div className="logo-mark">J</div>
          JobPilot <span style={{ color: 'var(--accent-soft)' }}>AI</span>
        </div>
        <nav className="nav">
          {TABS.map((t) => (
            <button key={t.id} className={tab === t.id ? 'active' : ''} onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </nav>
        <div className="provider-dot" title={Object.entries(providers).map(([k, v]) => `${k}: ${v.available ? v.model : 'not configured'}`).join('\n')}>
          <span className={`dot ${anyLLM ? 'on' : 'off'}`} />
          {anyLLM ? 'LLM ready' : 'Heuristic mode'}
        </div>
      </header>

      <main className="page">
        {tab === 'dashboard' && <Dashboard refreshKey={refreshKey} onOpenJob={setSelectedJob} onGoFind={() => setTab('find')} />}
        {tab === 'find' && <FindJobs refreshKey={refreshKey} onOpenJob={setSelectedJob} notify={notify} onChanged={refresh} />}
        {tab === 'tracker' && <Tracker refreshKey={refreshKey} onOpenJob={setSelectedJob} notify={notify} onChanged={refresh} />}
        {tab === 'profile' && <ProfilePage notify={notify} onChanged={refresh} />}
      </main>

      {selectedJob !== null && (
        <JobDetail
          jobId={selectedJob}
          onClose={() => setSelectedJob(null)}
          notify={notify}
          onChanged={refresh}
        />
      )}
      {toast && <div className={`toast ${toast.error ? 'error' : ''}`}>{toast.msg}</div>}
    </>
  );
}