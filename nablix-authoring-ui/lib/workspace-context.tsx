'use client';

import { createContext, useContext } from 'react';
import type { TopicContent, TopicWorkspace } from './api/contracts';

interface WorkspaceValue {
  workspace: TopicWorkspace;
  content: TopicContent | null;
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

/** The current topic workspace (tree, details, coverage). Null while loading. */
export function useWorkspace(): TopicWorkspace | null {
  return useContext(WorkspaceContext)?.workspace ?? null;
}

/** Section content (§6–§15) for the current topic. Null while loading. */
export function useContent(): TopicContent | null {
  return useContext(WorkspaceContext)?.content ?? null;
}
