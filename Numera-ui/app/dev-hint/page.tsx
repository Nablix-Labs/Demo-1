'use client';
import ScaffoldPanel from '@/components/ScaffoldPanel';
export default function DevScaffold() {
  const scaffold = { stepNumber: 1, totalSteps: 4, stepText: 'What changes?' } as never;
  return (
    <div style={{ width:'100vw', height:'100vh', background:'#EEF1F6', display:'grid', placeItems:'center' }}>
      <div id="stage" style={{ width:900, height:440, background:'#fff', borderRadius:16, position:'relative', overflow:'hidden' }}>
        <div className="absolute top-[26px] left-[34px] right-[34px] z-10">
          <div className="flex items-start gap-3 pr-[150px]">
            <div className="w-[30px] h-[30px] rounded-md border border-muted-gray bg-reading-surface flex items-center justify-center text-xs font-semibold text-slate-blue flex-shrink-0">1</div>
            <div className="text-[22px] leading-snug text-ink">3 + 5, 4 + 5, 5 + 5 &nbsp;—&nbsp; Write the general rule.</div>
          </div>
          <div className="mt-3 w-[min(560px,100%)]"><ScaffoldPanel scaffold={scaffold} /></div>
        </div>
      </div>
    </div>
  );
}
