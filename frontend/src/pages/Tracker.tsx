import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import type { Application, AppStatus } from '../types';
import { ROUNDS, SOURCE_LABELS, STATUS_LABELS } from '../types';

const COLUMNS: { id: AppStatus; color: string }[] = [
  { id: 'saved', color: 'var(--text-faint)' },
  { id: 'applied', color: 'var(--blue)' },
  { id: 'in_process', color: 'var(--yellow)' },
  { id: 'offer', color: 'var(--green)' },
  { id: 'rejected', color: 'var(--red)' },
  { id: 'ghosted', color: 'var(--text-faint)' },
];

export default function Tracker({ refreshKey, onOpenJob, notify, onChanged }: {
  refreshKey: number;
  onOpenJob: (id: number) => void;
  notify: (msg: string, error?: boolean) => void;
  onChanged: () => void;
}) {
  const [apps, setApps] = useState<Application[]>([]);
  const [dragOver, setDragOver] = useState<AppStatus | null>(null);
  const [dragging, setDragging] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    api.listApplications().then(setApps).catch((e) => notify(e.message, true)).finally(() => setLoading(false));
  }, [notify]);

  useEffect(() => { load(); }, [load, refreshKey]);

  const move = async (app: Application, status: AppStatus, round?: string) => {
    try {
      await api.updateApplication(app.id, {
        status,
        ...(round !== undefined ? { current_round: round } : {}),
      });
      load();
      onChanged();
    } catch (e) {
      notify((e as Error).message, true);
    }
  };

  const onDrop = (status: AppStatus) => {
    setDragOver(null);
    const app = apps.find((a) => a.id === dragging);
    setDragging(null);
    if (!app || app.status === status) return;
    void move(app, status, status === 'in_process' ? app.current_round || 'Screening' : '');
    notify(`Moved to ${STATUS_LABELS[status]}`);
  };

  const remove = async (app: Application) => {
    try {
      await api.deleteApplication(app.id);
      notify('Removed from tracker');
      load();
      onChanged();
    } catch (e) {
      notify((e as Error).message, true);
    }
  };

  if (loading) return <div className="empty-state"><div className="spinner" style={{ margin: '0 auto' }} /></div>;

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-title">Application Tracker</div>
          <div className="page-sub">Drag cards between stages · set the round for in-process applications</div>
        </div>
        <span className="badge accent">{apps.length} tracked</span>
      </div>

      <div className="kanban">
        {COLUMNS.map((col) => {
          const colApps = apps.filter((a) => a.status === col.id);
          return (
            <div
              key={col.id}
              className={`kanban-col ${dragOver === col.id ? 'drag-over' : ''}`}
              onDragOver={(e) => { e.preventDefault(); setDragOver(col.id); }}
              onDragLeave={() => setDragOver((d) => (d === col.id ? null : d))}
              onDrop={() => onDrop(col.id)}
            >
              <div className="kanban-col-header">
                <span className="kanban-col-title">
                  <span className="dot" style={{ background: col.color }} />
                  {STATUS_LABELS[col.id]}
                </span>
                <span className="kanban-count">{colApps.length}</span>
              </div>
              <div className="kanban-cards">
                {colApps.length === 0 && <div className="kanban-empty">Drop jobs here</div>}
                {colApps.map((app) => (
                  <div
                    key={app.id}
                    className={`kanban-card ${dragging === app.id ? 'dragging' : ''}`}
                    draggable
                    onDragStart={() => setDragging(app.id)}
                    onDragEnd={() => { setDragging(null); setDragOver(null); }}
                    onClick={() => app.job && onOpenJob(app.job.id)}
                  >
                    <div className="kanban-card-title">{app.job?.title ?? `Job #${app.job_id}`}</div>
                    <div className="kanban-card-company">{app.job?.company}</div>
                    <div className="kanban-card-meta">
                      {app.job && <span className="badge accent">{SOURCE_LABELS[app.job.source] ?? app.job.source}</span>}
                      {app.job && <span className="badge">{Math.round(app.job.match_score)}% match</span>}
                      {app.applied_at && <span className="badge blue">{new Date(app.applied_at).toLocaleDateString()}</span>}
                    </div>
                    {app.status === 'in_process' && (
                      <select
                        value={app.current_round}
                        onClick={(e) => e.stopPropagation()}
                        onChange={(e) => move(app, 'in_process', e.target.value)}
                      >
                        <option value="">Select round…</option>
                        {ROUNDS.map((r) => <option key={r} value={r}>{r}</option>)}
                      </select>
                    )}
                    <div onClick={(e) => e.stopPropagation()} style={{ marginTop: 8, display: 'flex', justifyContent: 'flex-end' }}>
                      <button className="btn sm ghost danger" title="Remove from tracker" onClick={() => remove(app)}>✕</button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}