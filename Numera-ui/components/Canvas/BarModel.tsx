'use client';

/**
 * BarModel — visual representation of 2x + 5 = 13
 * Rendered as plain rectangles (wireframe style).
 * In production the backend will control which visual is shown.
 */
export default function BarModel() {
  return (
    <div
      className="absolute flex flex-col gap-[18px] items-center"
      style={{ top: 96, left: '50%', transform: 'translateX(-50%)' }}
      aria-label="Bar model visual for 2x + 5 = 13"
    >
      {/* Total row */}
      <div className="flex flex-col gap-1 items-start w-full">
        <span className="text-[10px] tracking-widest uppercase text-[#9a9a9a]">Total</span>
        <div className="flex gap-1.5">
          <div
            className="h-14 bg-[#f4f4f4] border border-[#1a1a1a] rounded-[3px] flex items-center justify-center text-lg font-['Cambria_Math',Georgia,serif]"
            style={{ width: 396 }}
          >
            13
          </div>
        </div>
      </div>

      {/* Breakdown row */}
      <div className="flex flex-col gap-1 items-start w-full">
        <span className="text-[10px] tracking-widest uppercase text-[#9a9a9a]">Broken down</span>
        <div className="flex gap-1.5">
          {/* x cell */}
          <div
            className="h-14 bg-white border border-dashed border-[#1a1a1a] rounded-[3px] flex items-center justify-center text-lg font-['Cambria_Math',Georgia,serif] italic"
            style={{ width: 120 }}
          >
            x
          </div>
          {/* x cell */}
          <div
            className="h-14 bg-white border border-dashed border-[#1a1a1a] rounded-[3px] flex items-center justify-center text-lg font-['Cambria_Math',Georgia,serif] italic"
            style={{ width: 120 }}
          >
            x
          </div>
          {/* 5 cell */}
          <div
            className="h-14 bg-[#f4f4f4] border border-[#1a1a1a] rounded-[3px] flex items-center justify-center text-lg font-['Cambria_Math',Georgia,serif]"
            style={{ width: 150 }}
          >
            5
          </div>
        </div>
      </div>

      {/* Working out */}
      <div
        className="text-[26px] text-[#8a8a8a] mt-1.5"
        style={{ fontFamily: '"Comic Sans MS","Bradley Hand","Segoe Print",cursive' }}
      >
        2x = 8
      </div>
    </div>
  );
}
