import { act, createElement } from 'react';
import { createRoot } from 'react-dom/client';
import { expect, it } from 'vitest';
import VisualCue from '@/components/VisualCue';
import { useNumeraStore } from '@/store/useNumeraStore';

it('renders generated comparison rows inside the authorised cue', async () => {
  const before = useNumeraStore.getState();
  useNumeraStore.setState({
    currentPhase: 'GUIDED_PRACTICE', visualCueVisible: true,
    visualCueId: 'GENERATED:TEST', visualCueType: null,
    visualCueAssetUrl: null, visualCueDescription: 'Compare these different examples.',
    visualCueActions: [{ action: 'COMPARE_EXPRESSIONS', rows: [
      { expression: '2 + 3', annotation: 'Start at two and add three.' },
      { expression: '8 + 3', annotation: 'Start at eight and add three.' },
    ] }],
  });
  const container = document.createElement('div');
  const root = createRoot(container);
  try {
    await act(async () => root.render(createElement(VisualCue)));
    const table = container.querySelector('table[aria-label="Compare these examples"]');
    expect(table).not.toBeNull();
    expect(table?.querySelectorAll('tr')).toHaveLength(2);
    expect(table?.textContent).toContain('2 + 3');
    expect(table?.textContent).toContain('Start at eight and add three.');
  } finally {
    await act(async () => root.unmount());
    useNumeraStore.setState(before);
  }
});
