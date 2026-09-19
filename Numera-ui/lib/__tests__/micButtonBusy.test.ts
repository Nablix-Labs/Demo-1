/**
 * #330: while the tutor talks or thinks, the mic button must not invite an
 * answer. A live orange button did, students answered over and over, and the
 * flow collapsed under the extra turns.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { act } from 'react';
import FloatingMicButton from '@/components/FloatingMicButton';
import { useNumeraStore } from '@/store/useNumeraStore';
import { useAuthStore } from '@/store/useAuthStore';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let root: Root;
const button = () => host.querySelector('button')!;

beforeEach(() => {
  useAuthStore.setState({
    consents: {
      ...useAuthStore.getState().consents,
      voice_processing: { acceptedAt: '2026-09-19T00:00:00Z', withdrawnAt: null },
    } as never,
  });
  useNumeraStore.setState({ micMuted: false, voiceStatus: 'listening' });
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
  act(() => root.render(createElement(FloatingMicButton)));
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

describe('mic button while the tutor has the floor', () => {
  it.each(['speaking', 'processing'] as const)('ignores taps while %s', (status) => {
    act(() => useNumeraStore.setState({ voiceStatus: status }));
    expect(button().getAttribute('aria-disabled')).toBe('true');
    act(() => button().click());
    expect(useNumeraStore.getState().micMuted).toBe(false);
  });

  it('works again once it is the student’s turn', () => {
    act(() => useNumeraStore.setState({ voiceStatus: 'listening' }));
    expect(button().getAttribute('aria-disabled')).toBe('false');
    act(() => button().click());
    expect(useNumeraStore.getState().micMuted).toBe(true);
  });
});
