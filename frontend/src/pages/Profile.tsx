import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import type { Profile } from '../types';

export default function ProfilePage({ notify, onChanged }: {
  notify: (msg: string, error?: boolean) => void;
  onChanged: () => void;
}) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [saving, setSaving] = useState(false);
  const [targetRoles, setTargetRoles] = useState('');
  const [locations, setLocations] = useState('');
  const [expStretch, setExpStretch] = useState(1.8);
  const [remoteOk, setRemoteOk] = useState(true);
  const [expYears, setExpYears] = useState(0);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.getProfile().then((p) => {
      setProfile(p);
      if (p) {
        setTargetRoles(p.target_roles.join(', '));
        setLocations(p.preferred_locations.join(', '));
        setExpStretch(Math.round(p.exp_stretch * 10) / 10);
        setRemoteOk(p.remote_ok);
        setExpYears(Math.round(p.experience_years * 10) / 10);
      }
    }).catch(() => {});
  }, []);

  const upload = async (file: File) => {
    setUploading(true);
    try {
      const p = await api.uploadResume(file);
      setProfile(p);
      setTargetRoles(p.target_roles.join(', '));
      setLocations(p.preferred_locations.join(', '));
      setExpYears(Math.round(p.experience_years * 10) / 10);
      notify(`Resume parsed: ${p.skills.length} skills, ${p.experience_years.toFixed(1)} yrs experience`);
      onChanged();
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setUploading(false);
    }
  };

  const savePrefs = async () => {
    setSaving(true);
    try {
      const p = await api.updateProfile({
        target_roles: targetRoles.split(',').map((s) => s.trim()).filter(Boolean),
        preferred_locations: locations.split(',').map((s) => s.trim()).filter(Boolean),
        exp_stretch: expStretch,
        remote_ok: remoteOk,
        experience_years: expYears,
      });
      setProfile(p);
      notify('Preferences saved');
      onChanged();
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-title">Your Profile</div>
          <div className="page-sub">Upload your resume — the parser agent extracts skills and experience</div>
        </div>
        {profile && (
          <button className="btn" onClick={() => fileRef.current?.click()} disabled={uploading}>
            {uploading ? 'Parsing…' : 'Upload New Resume'}
          </button>
        )}
      </div>

      <input
        ref={fileRef} type="file" accept=".pdf,.docx,.txt" hidden
        onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
      />

      {!profile && (
        <div
          className={`upload-zone ${dragOver ? 'dragover' : ''}`}
          onClick={() => !uploading && fileRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            const f = e.dataTransfer.files?.[0];
            if (f) void upload(f);
          }}
        >
          <div className="big">{uploading ? '⏳' : '📄'}</div>
          <h3>{uploading ? 'Parsing your resume…' : 'Drop your resume here'}</h3>
          <p className="muted">PDF, DOCX or TXT · max 5 MB · parsed locally by the SLM agent</p>
        </div>
      )}

      {profile && (
        <>
          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
              <div>
                <h3 style={{ fontSize: 17 }}>{profile.name || 'Candidate'}</h3>
                <div className="muted">{profile.current_role} · {profile.experience_years.toFixed(1)} years experience</div>
                <div className="muted" style={{ fontSize: 12 }}>{profile.email} {profile.phone && `· ${profile.phone}`}</div>
              </div>
              <span className="badge accent">{profile.resume_filename}</span>
            </div>
            <div className="mt">
              <div className="label muted" style={{ fontSize: 12, marginBottom: 8 }}>Detected skills ({profile.skills.length})</div>
              <div className="skill-cloud">
                {profile.skills.map((s) => <span key={s} className="skill-tag match">{s}</span>)}
              </div>
            </div>
          </div>

          <div className="profile-grid">
            <div className="card">
              <h3 style={{ fontSize: 15, marginBottom: 14 }}>Search Preferences</h3>
              <div className="field" style={{ marginBottom: 12 }}>
                <label>Target roles (comma-separated)</label>
                <input value={targetRoles} onChange={(e) => setTargetRoles(e.target.value)} placeholder="AI Engineer, ML Engineer" />
              </div>
              <div className="field" style={{ marginBottom: 12 }}>
                <label>Preferred locations (comma-separated)</label>
                <input value={locations} onChange={(e) => setLocations(e.target.value)} placeholder="Bengaluru, Pune, Remote" />
              </div>
              <div className="field" style={{ marginBottom: 12 }}>
                <label>Your experience (years)</label>
                <input type="number" step="0.1" min="0" max="40" value={expYears} onChange={(e) => setExpYears(Number(e.target.value))} />
              </div>
              <div className="field" style={{ marginBottom: 12 }}>
                <label>Experience stretch (+years) — show jobs requiring up to {(expYears + expStretch).toFixed(1)} yrs</label>
                <input type="number" step="0.5" min="0" max="5" value={expStretch} onChange={(e) => setExpStretch(Number(e.target.value))} />
              </div>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                <input type="checkbox" checked={remoteOk} onChange={(e) => setRemoteOk(e.target.checked)} style={{ minWidth: 0 }} />
                Include remote roles
              </label>
              <button className="btn primary" onClick={savePrefs} disabled={saving}>{saving ? 'Saving…' : 'Save Preferences'}</button>
            </div>

            <div>
              {profile.work_history.length > 0 && (
                <div className="card" style={{ marginBottom: 16 }}>
                  <h3 style={{ fontSize: 15, marginBottom: 8 }}>Work History</h3>
                  {profile.work_history.map((w, i) => (
                    <div className="timeline-item" key={i}>
                      <div className="timeline-title">{w.title} {w.company && `· ${w.company}`}</div>
                      <div className="timeline-sub">{w.start} — {w.end}</div>
                      {w.summary && <div className="timeline-sub">{w.summary}</div>}
                    </div>
                  ))}
                </div>
              )}
              {profile.projects.length > 0 && (
                <div className="card" style={{ marginBottom: 16 }}>
                  <h3 style={{ fontSize: 15, marginBottom: 8 }}>Projects</h3>
                  {profile.projects.map((p, i) => (
                    <div className="timeline-item" key={i}>
                      <div className="timeline-title">{p.name}</div>
                      {p.description && <div className="timeline-sub">{p.description}</div>}
                    </div>
                  ))}
                </div>
              )}
              {profile.education.length > 0 && (
                <div className="card">
                  <h3 style={{ fontSize: 15, marginBottom: 8 }}>Education</h3>
                  {profile.education.map((e, i) => (
                    <div className="timeline-item" key={i}>
                      <div className="timeline-title">{e.degree}</div>
                      <div className="timeline-sub">{e.institution} {e.year && `· ${e.year}`}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </>
  );
}