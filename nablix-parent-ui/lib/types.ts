/**
 * What the parent portal reads about a child.
 *
 * Field names follow the tutor backend so the HTTP adapter is a pass-through:
 *  - attempts      ← SessionSummary.per_question_history (QuestionAttemptRecord)
 *  - topics        ← Student Model journey_state + Phase 4 whole_topic_evidence
 *  - misconceptions← Phase 4 linked_misconceptions / misconception_recurrence_counts
 *  - consents      ← the guardian consent records captured at sign-up
 * None of these are readable by a parent today — see docs/BACKEND-ASKS.md.
 */

export type Evaluation = 'CORRECT' | 'PARTIALLY_CORRECT' | 'INCORRECT';

export type Phase =
  | 'PHASE_0_DIAGNOSTIC'
  | 'PHASE_1_ORIENTATION'
  | 'PHASE_2_GUIDED_LEARNING'
  | 'PHASE_3_INDEPENDENT_PRACTICE'
  | 'PHASE_4_REVIEW';

export type SkillStatus =
  | 'INDEPENDENTLY_VERIFIED'
  | 'VERIFIED_WITH_SUPPORT'
  | 'RESCUE_REQUIRED'
  | 'UNKNOWN';

export type MasteryStatus = 'NOT_STARTED' | 'IN_PROGRESS' | 'MASTERED' | 'REVIEW';

export interface Child {
  student_code: string;
  name: string;
  year_group: string;
}

export interface Attempt {
  question_text: string;
  phase: Phase;
  evaluation: Evaluation;
  topic_id: string;
  micro_skill_id: string;
  /** 0 = no hint; 1–3 = the hint rung used. */
  hint_level_used: number;
  scaffold_used: boolean;
  visual_cue_shown: boolean;
  /** Solved with no hint, scaffold or tutor rescue. */
  independent: boolean;
  /** Seconds from the question appearing to the answer. */
  time_taken_seconds: number;
  misconception_id: string | null;
  attempted_at: string;
}

export interface Session {
  session_id: string;
  topic_id: string;
  session_date: string;
  session_duration_seconds: number;
  phases_completed: Phase[];
  tutor_interventions: number;
  attempts: Attempt[];
}

export interface MicroSkill {
  id: string;
  label: string;
  description: string;
  status: SkillStatus;
}

export interface TopicProgress {
  topic_id: string;
  title: string;
  /** Subject strand, used to pick the cover art. */
  strand: 'algebra' | 'number' | 'geometry' | 'statistics';
  mastery_status: MasteryStatus;
  current_phase: Phase | null;
  phases_completed: Phase[];
  micro_skills: MicroSkill[];
  recommended_next_action: string | null;
  started_at: string | null;
  last_activity_at: string | null;
}

export interface Misconception {
  id: string;
  label: string;
  description: string;
  topic_id: string;
}

export type ConsentPurpose =
  | 'account_creation'
  | 'ai_tutor_usage'
  | 'canvas_processing'
  | 'voice_processing'
  | 'learning_analytics'
  | 'safety_monitoring'
  | 'marketing';

export interface ConsentRecord {
  purpose: ConsentPurpose;
  accepted_at: string | null;
  withdrawn_at: string | null;
}

export interface ChildData {
  child: Child;
  topics: TopicProgress[];
  sessions: Session[];
  misconceptions: Misconception[];
  consents: ConsentRecord[];
}
