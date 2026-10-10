/**
 * Demo defaults the lesson store needs while it is being created.
 *
 * Kept out of lib/api: api → useAuthStore → useNumeraStore → api is a cycle,
 * and the store reads DEMO_CONCEPT_ID at module init. A page that loaded
 * lib/api first (the Key Notes screen) hit "Cannot access 'DEMO_CONCEPT_ID'
 * before initialization". A leaf module has no cycle to lose.
 */
export const DEMO_CONCEPT_ID = 'ALG_LINEAR_ONE_STEP';
export const DEMO_QUESTION_ID = 'ALG_EQ_DIAG_001';
export const DEMO_PHASE = 'GUIDED_PRACTICE';
