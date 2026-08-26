/**
 * Tutor prose with `**…**` shown as emphasis rather than as characters.
 * See lib/tutorMarkdown for why only bold is handled.
 */
import { Fragment } from 'react';
import { TUTOR_EMPHASIS } from '@/lib/tutorMarkdown';

export default function TutorProse({ text }: { text: string }) {
  // split() on a single-group pattern puts the emphasised runs at odd indices.
  const parts = text.split(TUTOR_EMPHASIS);
  if (parts.length === 1) return <>{text}</>;
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1
          ? <strong key={i} className="font-semibold">{part}</strong>
          : <Fragment key={i}>{part}</Fragment>,
      )}
    </>
  );
}
