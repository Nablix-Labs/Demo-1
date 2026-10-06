import { TopicWorkspaceShell } from '@/components/nablix/TopicWorkspaceShell';

/**
 * Pages built ahead of time for the static export (the VM build). `_` is the
 * placeholder nginx serves for any other topic id — the pages read the real id
 * from the URL (useTopicId), so it renders whichever topic was asked for.
 */
export function generateStaticParams() {
  return ['_', 'ALG-KS3-01', 'ALG-ORI-02', 'ALG-ORI-03'].map((topicId) => ({ topicId }));
}

export default function TopicLayout({ children }: { children: React.ReactNode }) {
  return <TopicWorkspaceShell>{children}</TopicWorkspaceShell>;
}
