import { useEffect, useState } from 'react';
import { api } from '../api';
import type { Stats } from '../types';
import { SOURCE_LABELS, STATUS_LABELS, type AppStatus } from '../types';

const FUNNEL: { key: keyof Stats; label: string; color: string }[] = [
  { key: 'saved', label: 'Saved', color: 'var(--text-faint)' },
  { key: 'applied', label: 'Applied', color: 'var(--blue)' },
  { key: 'in_process', label: 'In Process', color: 'var(--yellow)' },
  { key: 'offer', label: 'Offers', color: 'var(--green)' },
  { key: 'rejected', label: 'Rejected', color: 'var(--red)' },
  { key: 'ghosted', label: 'No Response', color: 'var(--text-faint)' },
];

export default function Dashboard({ refreshKey, onOpenJob, onGoFind }: {
  refreshKey: number;
  onOpenJob: (id: number) => void;
  onGoFind: () => void;
}) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api.getStats().then(setStats).catch((e) => setError(e.message));
  }, [refreshKey]);

  if (error) return <div className="empty-state"><h3>Backend unreachable</h3><p>{error}</p><p className="mt">Start it: <code>cd backend && uvicorn app.main:app --port 8000</code></p></div>;
  if (!stats) return <div className="empty-state"><div className="spinner" style={{ margin: '0 auto' }} /></div>;

  const maxFunnel = Math.max(1, ...FUNNEL.map((f) => Number(stats[f.key]) || 0));
  const totalTracked = stats.saved + stats.applied + stats.in_process + stats.offer + stats.rejected + stats.ghosted;

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-title">Job Hunt Dashboard</div>
          <div className="page-sub">Your pipeline at a glance</div>
        </div>
        <button className="btn primary" onClick={onGoFind}>Find New Jobs</button>
      </div>

      <div className="stat-grid">
        <div className="stat-card accent"><div className="stat-label">Jobs Found</div><div className="stat-value">{stats.total_jobs}</div></div>
        <div className="stat-card blue"><div className="stat-label">Applied</div><div className="stat-value">{stats.applied + stats.in_process + stats.offer + stats.rejected + stats.ghosted}</div></div>
        <div className="stat-card yellow"><div className="stat-label">In Process</div><div className="stat-value">{stats.in_process}</div></div>
        <div className="stat-card green"><div className="stat-label">Offers</div><div className="stat-value">{stats.offer}</div></div>
        <div className="stat-card red"><div className="stat-label">Rejected</div><div className="stat-value">{stats.rejected}</div></div>
        <div className="stat-card"><div className="stat-label">Response Rate</div><div className="stat-value">{stats.response_rate}%</div></div>
      </div>

      <div className="two-col">
        <div className="card">
          <h3 style={{ marginBottom: 16, fontSize: 15 }}>Application Funnel</h3>
          {totalTracked === 0 ? (
            <p className="muted">Nothing tracked yet. Find jobs, save the good ones, and mark them applied as you go.</p>
          ) : (
            <div className="funnel">
              {FUNNEL.map((f) => (
                <div className="funnel-row" key={f.key}>
                  <span className="funnel-label">{f.label}</span>
                  <div className="funnel-bar" style={{ width: `${(Number(stats[f.key]) / maxFunnel) * 70}%`, background: f.color }} />
                  <span className="funnel-count">{Number(stats[f.key])}</span>
                </div>
              ))}
            </div>
          )}
          {Object.keys(stats.by_round).length > 0 && (
            <>
              <h3 style={{ margin: '20px 0 12px', fontSize: 15 }}>Active Rounds</h3>
              <div className="job-skills">
                {Object.entries(stats.by_round).map(([round, count]) => (
                  <span key={round} className="badge yellow">{round}: {count}</span>
                ))}
              </div>
            </>
          )}
        </div>

        <div className="card">
          <h3 style={{ marginBottom: 8, fontSize: 15 }}>Recent Activity</h3>
          {stats.recent_activity.length === 0 ? (
            <p className="muted">No activity yet.</p>
          ) : (
            stats.recent_activity.map((a, i) => (
              <div className="activity-item" key={i} style={{ cursor: 'pointer' }} onClick={() => onOpenJob(a.job_id)}>
                <div>
                  <div className="activity-title">{a.title}</div>
                  <div className="activity-sub">{a.company} → {STATUS_LABELS[a.status as AppStatus] ?? a.status}{a.round ? ` · ${a.round}` : ''}</div>
                </div>
                <span className="activity-time">{new Date(a.at).toLocaleDateString()}</span>
              </div>
            ))
          )}
        </div>
      </div>

      {Object.keys(stats.by_source).length > 0 && (
        <div className="card mt">
          <h3 style={{ marginBottom: 12, fontSize: 15 }}>Jobs by Source</h3>
          <div className="job-skills">
            {Object.entries(stats.by_source).map(([src, count]) => (
              <span key={src} className="badge accent">{SOURCE_LABELS[src] ?? src}: {count}</span>
            ))}
            <span className="badge">Avg match: {stats.avg_match_score}</span>
          </div>
        </div>
      )}
    </>
  );
}