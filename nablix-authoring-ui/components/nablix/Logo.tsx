/**
 * The portal mark: a nabla (∇, the symbol Nablix is named after) built from
 * three stacked bars that narrow to a point — content layers being reviewed
 * down to one decision — with a lime check-tick where they meet.
 */
export function Logo({ size = 36, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      role="img"
      aria-label="Nablix"
      className={className}
    >
      <rect width="40" height="40" fill="#0E1A33" />
      {/* The nabla, as three bars narrowing downward */}
      <path d="M7 9h26l-2.6 5H9.6z" fill="#FFFFFF" />
      <path d="M11.1 17h17.8l-2.6 5H13.7z" fill="#FFFFFF" fillOpacity="0.78" />
      <path d="M15.2 25h9.6L20 34z" fill="#CBF24A" />
      {/* Approval tick crossing the point */}
      <path d="M24.5 29.5l3 3 6-7" fill="none" stroke="#CBF24A" strokeWidth="2.6" strokeLinecap="square" />
    </svg>
  );
}
