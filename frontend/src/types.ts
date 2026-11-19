export interface ScoreBreakdown {
  semantic: number;
  skills: number;
  experience: number;
  exp_fit: 'fit' | 'stretch' | 'unknown' | 'out_of_range';
  matched_skills: string[];
  missing_skills: string[];
}

export interface Insights {
  why_match?: string[];
  gaps?: string[];
  talking_points?: string[];
  resume_tips?: string[];
}

export type AppStatus = 'saved' | 'applied' | 'in_process' | 'offer' | 'rejected' | 'ghosted';

export interface Application {
  id: number;
  job_id: number;
  status: AppStatus;
  current_round: string;
  notes: string;
  status_history: { from: string; to: string; round: string; at: string; note: string }[];
  applied_at: string | null;
  created_at: string;
  updated_at: string;
  job?: Job;
}

export interface Job {
  id: number;
  source: string;
  title: string;
  company: string;
  location: string;
  is_remote: boolean;
  salary: string;
  exp_min: number | null;
  exp_max: number | null;
  experience_text: string;
  description: string;
  skills: string[];
  url: string;
  posted_text: string;
  posted_at: string | null;
  fetched_at: string;
  match_score: number;
  score_breakdown: ScoreBreakdown;
  insights: Insights;
  enriched: boolean;
  application: Application | null;
}

export interface Profile {
  id: number;
  name: string;
  email: string;
  phone: string;
  current_role: string;
  experience_years: number;
  skills: string[];
  work_history: { title?: string; company?: string; start?: string; end?: string; summary?: string }[];
  education: { degree?: string; institution?: string; year?: string }[];
  projects: { name?: string; description?: string; tech?: string[] }[];
  certifications: string[];
  target_roles: string[];
  preferred_locations: string[];
  remote_ok: boolean;
  exp_stretch: number;
  resume_filename: string;
  updated_at: string | null;
}

export interface SearchRun {
  id: number;
  params: Record<string, unknown>;
  status: 'running' | 'completed' | 'failed';
  progress: string;
  stats: Record<string, unknown>;
  error: string;
  started_at: string;
  finished_at: string | null;
}

export interface Stats {
  total_jobs: number;
  saved: number;
  applied: number;
  in_process: number;
  offer: number;
  rejected: number;
  ghosted: number;
  response_rate: number;
  avg_match_score: number;
  by_source: Record<string, number>;
  by_round: Record<string, number>;
  recent_activity: { job_id: number; title: string; company: string; status: string; round: string; at: string }[];
}

export const STATUS_LABELS: Record<AppStatus, string> = {
  saved: 'Saved',
  applied: 'Applied',
  in_process: 'In Process',
  offer: 'Offer',
  rejected: 'Rejected',
  ghosted: 'No Response',
};

export const ROUNDS = [
  'Screening',
  'Assessment',
  'Technical Round 1',
  'Technical Round 2',
  'Technical Round 3',
  'Managerial Round',
  'HR Round',
  'Other',
];

export const SOURCE_LABELS: Record<string, string> = {
  naukri: 'Naukri',
  indeed: 'Indeed',
  linkedin: 'LinkedIn',
  glassdoor: 'Glassdoor',
  company_site: 'Company Site',
  hirist: 'Hirist',
  wellfound: 'Wellfound',
};