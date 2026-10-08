/**
 * Teacher Mode marks, shared by the offline demo (TeachBackClient) and the live
 * screen (ConnectedTeachBackClient): Numera drawn as the pupil, and its
 * thinking dots.
 */
import { cn } from '@/lib/cn';

/** Numera-as-learner mark: a softer, warm 'N' — visually the flip of the cool tutor mark. */
export function PupilMark({ size = 40, bob = false, puzzled = false }: { size?: number; bob?: boolean; puzzled?: boolean }) {
  return (
    <div
      className={cn('flex-shrink-0 relative', bob && 'teach-bob')}
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <div
        className="w-full h-full rounded-[30%] flex items-center justify-center font-bold text-white"
        style={{
          fontSize: size * 0.5,
          background: 'linear-gradient(150deg, #FFB44D 0%, #FF9F1C 55%, #F77F00 100%)',
          boxShadow: '0 4px 14px rgba(247,127,0,0.28)',
        }}
      >
        N
      </div>
      {puzzled && (
        <span
          className="absolute -top-1.5 -right-1.5 rounded-full bg-white text-[#B4600A] font-bold flex items-center justify-center border border-[#F4C77A]"
          style={{ width: size * 0.42, height: size * 0.42, fontSize: size * 0.26 }}
        >
          ?
        </span>
      )}
    </div>
  );
}

export function Thinking() {
  return (
    <span className="inline-flex items-center gap-1 py-0.5" aria-label="Numera is thinking">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-1.5 h-1.5 rounded-full bg-[#E0A94E] animate-bounce"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </span>
  );
}
