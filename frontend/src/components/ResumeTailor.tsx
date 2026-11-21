import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import type { AtsResult, TailorAnalysis } from '../types';
import { ScoreRing } from './JobCard';

const ATS_LABELS: [keyof AtsResult['components'], string][] = [
  ['keyword_match', 'Keyword match (40%)'],
  ['skills_coverage', 'Skills coverage (20%)'],
  ['title_match', 'Job-title match (15%)'],
  ['section_completeness', 'Sections + contact (15%)'],
  ['date_consistency', 'Date consistency (10%)'],
];

export default function ResumeTailor({ jobId, jobTitle, matchScore, onClose, notify }: {
  jobId: number;
  jobTitle: string;
  matchScore: number;
  onClose: () => void;
  notify: (msg: string, error?: boolean) => void;
}) {
  const [analysis, setAnalysis] = useState<TailorAnalysis | null>(null);
  const [content, setContent] = useState('');
  const [live, setLive] = useState<AtsResult | null>(null);
  const [saving, setSaving] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [draftNotes, setDraftNotes] = useState<string[]>([]);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    api.getTailor(jobId).then((a) => {
      setAnalysis(a);
      setContent(a.tailored?.content ?? a.master_content);
      setLive(a.tailored ? null : a.base_ats);
      if (a.tailored) {
        api.scoreTailor(jobId, a.tailored.content).then(setLive).catch(() => setLive(a.base_ats));
      }
    }).catch((e) => notify(e.message, true));
  }, [jobId, notify]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const rescore = useCallback((text: string) => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      api.scoreTailor(jobId, text).then(setLive).catch(() => {});
    }, 450);
  }, [jobId]);

  const edit = (text: string) => {
    setContent(text);
    rescore(text);
  };

  const addKeyword = (kw: string) => {
    setContent((c) => {
      const next = /TARGETED SKILLS:/i.test(c)
        ? c.replace(/TARGETED SKILLS:[^\n]*/i, (m) => (m.includes(kw) ? m : `${m}, ${kw}`))
        : `${c.trimEnd()}\nTARGETED SKILLS: ${kw}`;
      rescore(next);
      return next;
    });
  };

  const draft = async () => {
    setDrafting(true);
    try {
      const d = await api.draftTailor(jobId);
      edit(d.content);
      setDraftNotes(d.notes ?? []);
      notify(d.method === 'llm' ? 'AI draft generated' : 'Heuristic draft generated');
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setDrafting(false);
    }
  };

  const save = async () => {
    setSaving(true);
    try {
      const t = await api.saveTailor(jobId, content);
      setAnalysis((a) => (a ? { ...a, tailored: t } : a));
      notify(`Saved · ATS ${t.base_ats_score} → ${t.ats_score}`);
      return t;
    } catch (e) {
      notify((e as Error).message, true);
      return null;
    } finally {
      setSaving(false);
    }
  };

  const exportAs = async (format: 'txt' | 'docx') => {
    const t = await save();
    if (t) window.open(api.tailorExportUrl(jobId, format), '_blank', 'noopener');
  };

  if (!analysis) {
    return (
      <>
        <div className="drawer-overlay" onClick={onClose} />
        <div className="tailor-modal"><div className="spinner" style={{ margin: '40px auto' }} /></div>
      </>
    );
  }

  const base = analysis.base_ats.score;
  const cur = live?.score ?? base;
  const delta = Math.round((cur - base) * 10) / 10;
  const gaps = analysis.gaps;

  return (
    <>
      <div className="drawer-overlay" onClick={onClose} />
      <div className="tailor-modal">
        <button className="drawer-close" onClick={onClose}>✕</button>
        <div className="tailor-header">
          <div>
            <h2>Resume Tailor</h2>
            <div className="muted">{jobTitle} · {Math.round(matchScore)}% match · unlocked at {analysis.min_score}%+</div>
          </div>
          <div className="tailor-scores">
            <div className="tailor-score-block">
              <ScoreRing score={base} />
              <span className="muted">master ATS</span>
            </div>
            <span className={`ats-delta ${delta > 0 ? 'up' : delta < 0 ? 'down' : ''}`}>
              {delta > 0 ? `+${delta}` : delta}
            </span>
            <div className="tailor-score-block">
              <ScoreRing score={cur} />
              <span className="muted">tailored ATS</span>
            </div>
          </div>
        </div>

        {live && live.parse_warnings.length > 0 && (
          <div className="tailor-warnings">
            {live.parse_warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
          </div>
        )}

        <div className="tailor-grid">
          <div className="tailor-left">
            <div className="drawer-section">
              <h4>Safe to add ({gaps.add.length})</h4>
              <p className="muted" style={{ fontSize: 12 }}>Already in your resume under different wording — surface the exact JD term.</p>
              {gaps.add.length === 0 && <p className="muted">Nothing to rephrase; your resume already uses the JD's terms.</p>}
              {gaps.add.map((g) => (
                <div className="gap-card add" key={g.keyword}>
                  <div className="gap-head">
                    <span className="skill-tag match">{g.keyword}</span>
                    <button className="btn sm" onClick={() => addKeyword(g.keyword)}>+ insert</button>
                  </div>
                  {g.evidence && <div className="gap-evidence">“{g.evidence}”</div>}
                </div>
              ))}
            </div>
            <div className="drawer-section">
              <h4>Learn first ({gaps.learn.length})</h4>
              <p className="muted" style={{ fontSize: 12 }}>Real gaps — study these, do NOT claim them on your resume yet.</p>
              {gaps.learn.map((g) => (
                <div className="gap-card learn" key={g.keyword}>
                  <div className="gap-head"><span className="skill-tag miss">{g.keyword}</span></div>
                  <div className="gap-evidence">{g.why}</div>
                  {g.resource && <a className="gap-link" href={g.resource} target="_blank" rel="noopener noreferrer">Learn ↗</a>}
                </div>
              ))}
            </div>
            {live && (
              <div className="drawer-section">
                <h4>ATS components</h4>
                <div className="score-bars">
                  {ATS_LABELS.map(([key, label]) => (
                    <div className="score-bar-row" key={key}>
                      <span className="score-bar-label">{label}</span>
                      <div className="score-bar-track">
                        <div className="score-bar-fill" style={{ width: `${Math.round(live.components[key] * 100)}%` }} />
                      </div>
                      <span>{Math.round(live.components[key] * 100)}%</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="tailor-right">
            <div className="tailor-editor-head">
              <h4>Tailored resume</h4>
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn sm" onClick={draft} disabled={drafting}>{drafting ? 'Drafting…' : 'Auto-draft'}</button>
                <button className="btn sm primary" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
              </div>
            </div>
            <textarea
              className="tailor-editor"
              value={content}
              onChange={(e) => edit(e.target.value)}
              spellCheck={false}
            />
            {draftNotes.length > 0 && (
              <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
                {draftNotes.map((n, i) => <div key={i}>· {n}</div>)}
              </div>
            )}
            <div className="tailor-actions">
              <button className="btn" onClick={() => exportAs('txt')} disabled={saving}>Export TXT</button>
              <button className="btn" onClick={() => exportAs('docx')} disabled={saving}>Export DOCX</button>
              {analysis.tailored && (
                <span className="badge accent">saved · +{analysis.tailored.keywords_added.length} keywords</span>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}