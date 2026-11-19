import type { Job } from '../types';
import { SOURCE_LABELS, STATUS_LABELS } from '../types';

export function scoreColor(score: number): string {
  if (score >= 70) return 'var(--green)';
  if (score >= 50) return 'var(--yellow)';
  return 'var(--red)';
}

export function ScoreRing({ score }: { score: number }) {
  return (
    <div
      className="score-ring"
      style={{ '--pct': score, '--ring-color': scoreColor(score) } as React.CSSProperties}
      title={`Match score: ${score}`}
    >
      <span>{Math.round(score)}</span>
    </div>
  );
}

export function ExpBadge({ job }: { job: Job }) {
  const fit = job.score_breakdown?.exp_fit;
  const text = job.experience_text || (job.exp_min !== null ? `${job.exp_min}-${job.exp_max ?? '?'} yrs` : 'Exp. open');
  const cls = fit === 'fit' ? 'green' : fit === 'stretch' ? 'yellow' : 'blue';
  const label = fit === 'stretch' ? `${text} · stretch` : text;
  return <span className={`badge ${cls}`}>{label}</span>;
}

export default function JobCard({ job, onOpen, onSave, onApply }: {
  job: Job;
  onOpen: (id: number) => void;
  onSave: (id: number) => void;
  onApply: (job: Job) => void;
}) {
  const matched = new Set(job.score_breakdown?.matched_skills ?? []);
  const skills = (job.skills ?? []).slice(0, 6);
  return (
    <div className="card job-card" onClick={() => onOpen(job.id)}>
      <div className="job-card-top">
        <ScoreRing score={job.match_score} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="job-title">{job.title}</div>
          <div className="job-company">{job.company || 'Unknown company'}</div>
        </div>
        <span className="badge accent">{SOURCE_LABELS[job.source] ?? job.source}</span>
      </div>
      <div className="job-meta">
        <span className="badge">{job.location || 'Location N/A'}</span>
        {job.is_remote && <span className="badge purple">Remote</span>}
        <ExpBadge job={job} />
        {job.salary && <span className="badge">{job.salary}</span>}
        {job.application && <span className="badge blue">{STATUS_LABELS[job.application.status]}</span>}
      </div>
      {skills.length > 0 && (
        <div className="job-skills">
          {skills.map((s) => (
            <span key={s} className={`skill-tag ${matched.has(s.toLowerCase()) ? 'match' : ''}`}>{s}</span>
          ))}
        </div>
      )}
      <div className="job-card-actions" onClick={(e) => e.stopPropagation()}>
        {!job.application && (
          <button className="btn sm ghost" onClick={() => onSave(job.id)}>Save</button>
        )}
        <button className="btn sm primary" style={{ marginLeft: 'auto' }} onClick={() => onApply(job)}>
          Apply ↗
        </button>
      </div>
    </div>
  );
}