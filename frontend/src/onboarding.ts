import type { AuthUser } from './api';

const guideSeenPrefix = 'local_rag_guide_seen_';

function guideSeenKey(user: AuthUser | null) {
  return `${guideSeenPrefix}${user?.id || 'anonymous'}`;
}

export function hasSeenGuide(user: AuthUser | null) {
  if (!user) return true;
  return localStorage.getItem(guideSeenKey(user)) === '1';
}

export function markGuideSeen(user: AuthUser | null) {
  if (!user) return;
  localStorage.setItem(guideSeenKey(user), '1');
}
