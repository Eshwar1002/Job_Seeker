import { useEffect, useState } from 'react';
import { api } from '../api';
import type { AppStatus, Job } from '../types';
import { ROUNDS, SOURCE_LABELS, STATUS_LABELS } from '../types';
import { ExpBadge, ScoreRing } from './JobCard';

export default function JobDetail({ jobId, onClose, notify, onChanged }: {
  jobId: number;
  onClose: () => void;
  notify: (msg: string, error?: boolean) => void;
  onChanged: () => void;
}) {
  const [job, setJob] = useState<Job | null>(null);
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [enriching, setEnriching] = useState(false);

  useEffect(() => {
    api.getJob(jobId).then((j) => {
      setJob(j);
      setNotes(j.application?.notes ?? '');
    }).catch((e) => notify(e.message, true));
  }, [jobId, notify]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const setStatus = async (status: AppStatus, round?: string) => {
    if (!job) return;
    setBusy(true);
    try {
      if (job.application) {
        await api.updateApplication(job.application.id, {
          status,
          ...(round !== undefined ? { current_round: round } : {}),
          notes,
        });
      } else {
        await api.trackJob(job.id, status);
        if (round !== undefined || notes) {
          const fresh = await api.getJob(job.id);
          if (fresh.application) {
            await api.updateApplication(fresh.application.id, {
              ...(round !== undefined ? { current_round: round } : {}),
              notes,
            });
          }
        }
      }
      const fresh = await api.getJob(job.id);
      setJob(fresh);
      setNotes(fresh.application?.notes ?? '');
      notify(`Marked as ${STATUS_LABELS[status]}`);
      onChanged();
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  };

  const saveNotes = async () => {
    if (!job?.application) return;
    setBusy(true);
    try {
      await api.updateApplication(job.application.id, { notes });
      notify('Notes saved');
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  };

  const enrich = async () => {
    setEnriching(true);
    try {
      const fresh = await api.enrichJob(jobId);
      setJob(fresh);
      notify('Insights generated');
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setEnriching(false);
    }
  };

  const apply = () => {
    if (!job) return;
    window.open(job.url, '_blank', 'noopener');
    if (!job.application || job.application.status === 'saved') {
      void setStatus('applied');
    }
  };

  if (!job) {
    return (
      <>
        <div className="drawer-overlay" onClick={onClose} />
        <div className="drawer"><div className="spinner" /></div>
      </>
    );
  }

  const bd = job.score_breakdown;
  const app = job.application;

  return (
    <>
      <div className="drawer-overlay" onClick={onClose} />
      <div className="drawer">
        <button className="drawer-close" onClick={onClose}>✕</button>
        <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
          <ScoreRing score={job.match_score} />
          <div>
            <h2>{job.title}</h2>
            <div className="muted">{job.company} · {job.location}</div>
            <div className="job-meta" style={{ marginTop: 8 }}>
              <span className="badge accent">{SOURCE_LABELS[job.source] ?? job.source}</span>
              <ExpBadge job={job} />
              {job.is_remote && <span className="badge purple">Remote</span>}
              {job.salary && <span className="badge">{job.salary}</span>}
              {job.posted_text && <span className="badge">Posted {job.posted_text}</span>}
            </div>
          </div>
        </div>

        <div className="drawer-section">
          <div className="status-controls">
            <button className="btn primary" onClick={apply}>Apply on {SOURCE_LABELS[job.source] ?? job.source} ↗</button>
            {(!app || app.status === 'saved') && (
              <button className="btn" disabled={busy} onClick={() => setStatus('applied')}>Mark Applied</button>
            )}
            {app && app.status !== 'saved' && (
              <select
                value={app.status}
                disabled={busy}
                onChange={(e) => setStatus(e.target.value as AppStatus)}
              >
                {Object.entries(STATUS_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            )}
            {app?.status === 'in_process' && (
              <select
                value={app.current_round}
                disabled={busy}
                onChange={(e) => setStatus('in_process', e.target.value)}
              >
                <option value="">Select round…</option>
                {ROUNDS.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            )}
          </div>
          {app && (
            <div style={{ marginTop: 10 }}>
              <textarea
                rows={2}
                style={{ width: '100%' }}
                placeholder="Notes (recruiter name, referral, next steps…)"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                onBlur={saveNotes}
              />
            </div>
          )}
        </div>

        <div className="drawer-section">
          <h4>Match breakdown</h4>
          <div className="score-bars">
            {([['Semantic fit', bd?.semantic], ['Skills overlap', bd?.skills], ['Experience fit', bd?.experience]] as const).map(([label, val]) => (
              <div className="score-bar-row" key={label}>
                <span className="score-bar-label">{label}</span>
                <div className="score-bar-track">
                  <div className="score-bar-fill" style={{ width: `${Math.round((val ?? 0) * 100)}%` }} />
                </div>
                <span>{Math.round((val ?? 0) * 100)}%</span>
              </div>
            ))}
          </div>
          {(bd?.matched_skills?.length ?? 0) > 0 && (
            <div className="job-skills" style={{ marginTop: 10 }}>
              {bd.matched_skills.map((s) => <span key={s} className="skill-tag match">{s}</span>)}
              {bd.missing_skills?.map((s) => <span key={s} className="skill-tag miss">{s}</span>)}
            </div>
          )}
        </div>

        <div className="drawer-section">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <h4>AI insights</h4>
            <button className="btn sm ghost" onClick={enrich} disabled={enriching}>
              {enriching ? 'Thinking…' : job.enriched ? 'Regenerate' : 'Generate'}
            </button>
          </div>
          {job.enriched ? (
            <>
              {job.insights.why_match?.length ? (
                <div className="mt"><strong style={{ fontSize: 13 }}>Why you match</strong>
                  <ul>{job.insights.why_match.map((t, i) => <li key={i}>{t}</li>)}</ul></div>
              ) : null}
              {job.insights.gaps?.length ? (
                <div className="mt"><strong style={{ fontSize: 13 }}>Gaps to address</strong>
                  <ul>{job.insights.gaps.map((t, i) => <li key={i}>{t}</li>)}</ul></div>
              ) : null}
              {job.insights.talking_points?.length ? (
                <div className="mt"><strong style={{ fontSize: 13 }}>Talking points</strong>
                  <ul>{job.insights.talking_points.map((t, i) => <li key={i}>{t}</li>)}</ul></div>
              ) : null}
              {job.insights.resume_tips?.length ? (
                <div className="mt"><strong style={{ fontSize: 13 }}>Resume tips</strong>
                  <ul>{job.insights.resume_tips.map((t, i) => <li key={i}>{t}</li>)}</ul></div>
              ) : null}
            </>
          ) : (
            <p className="muted">Generate tailored insights for this job (uses your resume as context).</p>
          )}
        </div>

        {app && app.status_history.length > 0 && (
          <div className="drawer-section">
            <h4>History</h4>
            {app.status_history.slice().reverse().map((h, i) => (
              <div key={i} className="activity-sub" style={{ padding: '4px 0' }}>
                {new Date(h.at).toLocaleDateString()} — {STATUS_LABELS[h.to as AppStatus] ?? h.to}
                {h.round ? ` (${h.round})` : ''}{h.note ? ` · ${h.note}` : ''}
              </div>
            ))}
          </div>
        )}

        <div className="drawer-section">
          <h4>Job description</h4>
          <div className="jd-text">{job.description || 'No description captured — open the posting for full details.'}</div>
        </div>
      </div>
    </>
  );
}