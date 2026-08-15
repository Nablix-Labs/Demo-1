'use client';

import { useSearchParams } from 'next/navigation';

/**
 * A record the user arrived at from a validation issue or coverage cell.
 *
 * The contract is explicit that default_selection decides where a page opens.
 * This is the one sanctioned exception: when navigate_to metadata named a
 * specific record, that record wins for this navigation only. Pages should fall
 * back to default_selection whenever these are absent.
 */
export function useSelectionOverride() {
  const params = useSearchParams();
  return {
    select: params.get('select') ?? undefined,
    tab: params.get('tab') ?? undefined,
    phase: params.get('phase') ?? undefined,
  };
}
