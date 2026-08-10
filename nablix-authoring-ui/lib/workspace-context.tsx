'use client';

import { createContext, useContext } from 'react';
import type { CoverageData, TopicDetailsData } from './api/v3-contracts';

interface WorkspaceValue {
  workspace: TopicDetailsData;
  coverage: CoverageData | null;
}

const WorkspaceContext = createContext<WorkspaceValue | null>(null);

export function WorkspaceProvider({
  value,
  children,
}: {
  value: WorkspaceValue;
  children: React.ReactNode;
}) {
  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

/** Topic header and hierarchy counts for the open workspace. Null while loading. */
export function useWorkspace(): TopicDetailsData | null {
  return useContext(WorkspaceContext)?.workspace ?? null;
}

/** Coverage grid and validation for the open workspace. Null while loading. */
export function useCoverage(): CoverageData | null {
  return useContext(WorkspaceContext)?.coverage ?? null;
}
