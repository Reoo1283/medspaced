export type Role = "student" | "reviewer" | "admin";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

export interface Skill {
  id: string;
  title: string;
  category: string;
  description: string;
  parent_id: string | null;
  prerequisites: string[];
  mastery_score: number;
  unlocked: boolean;
}

export interface SkillNode extends Skill {
  children: SkillNode[];
}

export interface SkillProgress {
  skill_id: string;
  title: string;
  category: string;
  mastery_score: number;
  unlocked: boolean;
  last_practiced_at: string | null;
}

export interface Source {
  chunk_id: string;
  file_id: string;
  filename: string;
  section_title: string;
  page_number: number | null;
  snippet: string;
}

export interface StudyItem {
  exercise_id: string;
  skill_id: string | null;
  skill_title: string | null;
  type: "mcq" | "cloze" | "matching" | "vignette";
  payload: {
    stem?: string;
    options?: string[];
    text?: string;
    vignette?: string;
    prompt?: string;
    left?: string[];
    right?: string[];
    [key: string]: unknown;
  };
  source: Source | null;
  state: string;
  due_at: string | null;
  retrievability: number | null;
  rotation_match: boolean;
}

export interface Personalization {
  desired_retention: number;
  strategy: string;
  reviews_analyzed: number;
  accuracy: number | null;
  lapse_rate: number | null;
  parameter_count: number;
  optimized_at: string | null;
}

export interface ReviewResult {
  exercise_id: string;
  is_correct: boolean;
  correct_answer: Record<string, unknown> | null;
  explanation: string | null;
  rating: string;
  next_due_at: string | null;
  interval_days: number;
  xp_awarded: number;
  total_xp: number;
  current_streak: number;
  mastery_score: number | null;
  ability_theta: number;
  ability_se: number;
  exercise_difficulty: number;
}

export interface StudyStats {
  ability_theta: number;
  ability_se: number;
  rotation: string | null;
  due_count: number;
  new_count: number;
  approved_exercise_count: number;
  mastered_skill_count: number;
  total_xp: number;
  weekly_xp: number;
  league: string;
  current_streak: number;
  longest_streak: number;
  reviews_today: number;
  last_active_date: string | null;
}

export interface ContentFile {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  status: string;
  error_message: string | null;
  uploaded_by: string | null;
  processed_at: string | null;
  created_at: string;
  chunk_count: number;
  exercise_count: number;
}

export interface Job {
  id: string;
  kind: string;
  status: string;
  progress: number;
  message: string | null;
  payload: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface Exercise {
  id: string;
  skill_id: string | null;
  skill_title: string | null;
  concept_id: string | null;
  type: string;
  status: string;
  payload: Record<string, any>;
  difficulty: number;
  source: Source | null;
  generation_meta: Record<string, unknown> | null;
  reviewed_at: string | null;
  rejection_reason: string | null;
  created_at: string;
}

export interface ReviewCounts {
  draft: number;
  under_review: number;
  approved: number;
  rejected: number;
}

export interface ExamQuestion {
  exercise_id: string;
  skill_id: string | null;
  skill_title: string | null;
  type: "mcq" | "cloze" | "matching" | "vignette";
  payload: {
    stem?: string;
    options?: string[];
    text?: string;
    vignette?: string;
    prompt?: string;
    left?: string[];
    right?: string[];
  };
}

export interface ExamSession {
  session_id: string;
  started_at: string;
  expires_at: string;
  duration_minutes: number;
  questions: ExamQuestion[];
}

export interface ExamItemResult {
  exercise_id: string;
  is_correct: boolean;
  correct_answer: Record<string, unknown> | null;
  explanation: string | null;
  score: number | null;
}

export interface ExamResult {
  score: number;
  correct_count: number;
  total: number;
  xp_awarded: number;
  total_xp: number;
  league: string;
  current_streak: number;
  duration_seconds: number;
  details: ExamItemResult[];
}
