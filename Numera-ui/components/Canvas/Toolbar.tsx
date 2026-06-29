'use client';

import { useEffect, useRef, useState } from 'react';
import {
  Pen, Pencil, Highlighter, Eraser, Ruler, Square, Circle, Triangle,
  Undo2, Redo2, CheckCircle2, Trash2, MousePointerClick, Brush,
  GripVertical, GripHorizontal, ChevronDown,
} from 'lucide-react';
import { useNumeraStore, type ShapeKind, type EraserMode } from '@/store/useNumeraStore';
import { cn } from '@/lib/cn';

interface ToolbarProps {
  onCheckWork: () => void;
}

const COLORS = ['#1a1a1a', '#7a7a7a', '#b0b0b0', '#2563eb', '#dc2626'];
const SHAPES: { kind: ShapeKind; Icon: typeof Square; label: string }[] = [
  { kind: 'rect', Icon: Square, label: 'Rectangle' },
  { kind: 'circle', Icon: Circle, label: 'Circle' },
  { kind: 'triangle', Icon: Triangle, label: 'Triangle' },
];

export default function Toolbar({ onCheckWork }: ToolbarProps) {
  const {
    activeTool, shapeKind, eraserMode, strokeColor, strokeWidth, items, undone,
    setActiveTool, setShapeKind, setEraserMode, setStrokeColor, setStrokeWidth,
    undo, redo, clearCanvas,
    toolbarPos, setToolbarPos, toolbarCollapsed, toggleToolbarCollapsed,
    toolbarOrientation, setToolbarOrientation,
  } = useNumeraStore();

  const [menu, setMenu] = useState<'color' | 'shapes' | 'eraser' | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const dragOffset = useRef<{ dx: number; dy: number } | null>(null);

  const vertical = toolbarOrientation === 'vertical';

  // Close any open popover on outside click / Escape
  useEffect(() => {
    if (!menu) return;
    const onDoc = (e: MouseEvent) => { if (rootRef.current && !rootRef.current.contains(e.target as Node)) setMenu(null); };
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setMenu(null);
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey); };
  }, [menu]);

  // ── Drag — move the palette; rotate to vertical when docked at a side ────────
  const onHandleDown = (e: React.PointerEvent) => {
    const el = rootRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    dragOffset.current = { dx: e.clientX - r.left, dy: e.clientY - r.top };
    el.setPointerCapture(e.pointerId);
    e.preventDefault();
    e.stopPropagation();
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragOffset.current) return;
    const el = rootRef.current;
    const parent = el?.offsetParent as HTMLElement | null;
    if (!el || !parent) return;
    const pr = parent.getBoundingClientRect();
    const w = el.offsetWidth, h = el.offsetHeight;
    const x = Math.max(8, Math.min(e.clientX - pr.left - dragOffset.current.dx, pr.width - w - 8));
    const y = Math.max(8, Math.min(e.clientY - pr.top - dragOffset.current.dy, pr.height - h - 8));
    setToolbarPos({ x, y });
    // Dock-aware orientation: hug a vertical edge → go vertical
    const o = (x <= 24 || x >= pr.width - w - 24) ? 'vertical' : 'horizontal';
    if (o !== toolbarOrientation) setToolbarOrientation(o);
  };
  const onPointerUp = (e: React.PointerEvent) => {
    dragOffset.current = null;
    try { rootRef.current?.releasePointerCapture(e.pointerId); } catch { /* noop */ }
  };

  const positioned = toolbarPos != null;
  const canUndo = items.length > 0;
  const canRedo = undone.length > 0;

  const Sep = () => <div className={cn('bg-[#c8c8c8]', vertical ? 'h-[1.5px] w-[22px] my-0.5' : 'w-[1.5px] h-[22px] mx-0.5')} />;
  const btn = (active: boolean) =>
    cn('w-9 h-9 rounded-full flex items-center justify-center transition-colors flex-shrink-0',
      active ? 'bg-[#1a1a1a] text-white' : 'bg-transparent text-[#1a1a1a] hover:bg-[#f4f4f4]');
  // Popovers open away from the bar: to the side when vertical, upward when horizontal.
  const popPos = vertical ? 'left-[calc(100%+10px)] top-0' : 'bottom-[calc(100%+10px)] left-1/2 -translate-x-1/2';

  const ActiveToolIcon =
    activeTool === 'pen' ? Pen : activeTool === 'pencil' ? Pencil
    : activeTool === 'highlighter' ? Highlighter
    : activeTool === 'eraser' ? Eraser : activeTool === 'ruler' ? Ruler
    : SHAPES.find((s) => s.kind === shapeKind)!.Icon;

  return (
    <div
      ref={rootRef}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      className={cn(
        'absolute z-20 flex items-center gap-[5px] bg-white border border-[#9a9a9a] rounded-[24px] px-[9px] py-[6px] select-none',
        vertical ? 'flex-col' : 'flex-row',
        !positioned && 'bottom-5 left-1/2 -translate-x-1/2'
      )}
      style={{ boxShadow: '0 2px 12px rgba(0,0,0,0.10)', ...(positioned ? { left: toolbarPos!.x, top: toolbarPos!.y } : {}) }}
      role="toolbar"
      aria-label="Drawing tools"
    >
      {/* drag handle */}
      <button
        onPointerDown={onHandleDown}
        title="Drag to move" aria-label="Move toolbar"
        className="flex items-center justify-center w-5 h-9 text-[#9a9a9a] hover:text-[#1a1a1a] cursor-grab active:cursor-grabbing touch-none flex-shrink-0"
      >
        {vertical ? <GripHorizontal size={16} strokeWidth={1.6} /> : <GripVertical size={16} strokeWidth={1.6} />}
      </button>

      {toolbarCollapsed ? (
        <button onClick={toggleToolbarCollapsed} title="Expand toolbar" aria-label="Expand toolbar" className="w-9 h-9 rounded-full bg-[#1a1a1a] text-white flex items-center justify-center">
          <ActiveToolIcon size={18} strokeWidth={1.7} />
        </button>
      ) : (
        <>
          <button title="Pen" aria-label="pen" aria-pressed={activeTool === 'pen'} onClick={() => setActiveTool('pen')} className={btn(activeTool === 'pen')}>
            <Pen size={18} strokeWidth={1.7} />
          </button>
          <button title="Pencil" aria-label="pencil" aria-pressed={activeTool === 'pencil'} onClick={() => setActiveTool('pencil')} className={btn(activeTool === 'pencil')}>
            <Pencil size={18} strokeWidth={1.7} />
          </button>
          <button title="Highlighter" aria-label="highlighter" aria-pressed={activeTool === 'highlighter'} onClick={() => setActiveTool('highlighter')} className={btn(activeTool === 'highlighter')}>
            <Highlighter size={18} strokeWidth={1.7} />
          </button>

          {/* Eraser with options */}
          <div className="relative flex-shrink-0">
            <button title="Eraser" aria-label="eraser" aria-pressed={activeTool === 'eraser'} aria-expanded={menu === 'eraser'}
              onClick={() => { setActiveTool('eraser'); setMenu(menu === 'eraser' ? null : 'eraser'); }} className={btn(activeTool === 'eraser')}>
              <Eraser size={18} strokeWidth={1.7} />
            </button>
            {menu === 'eraser' && (
              <Popover pos={popPos}>
                <MenuItem active={eraserMode === 'stroke'} icon={<Brush size={15} strokeWidth={1.7} />} label="Erase (rub)" onClick={() => { setEraserMode('stroke'); setMenu(null); }} />
                <MenuItem active={eraserMode === 'object'} icon={<MousePointerClick size={15} strokeWidth={1.7} />} label="Delete object" onClick={() => { setEraserMode('object'); setMenu(null); }} />
                <div className="h-[1px] bg-[#eaeaea] my-1" />
                <MenuItem icon={<Trash2 size={15} strokeWidth={1.7} />} label="Clear all" onClick={() => { clearCanvas(); setMenu(null); }} />
              </Popover>
            )}
          </div>

          {/* Shapes with picker */}
          <div className="relative flex-shrink-0">
            <button title="Shapes" aria-label="shapes" aria-pressed={activeTool === 'shape'} aria-expanded={menu === 'shapes'}
              onClick={() => { setActiveTool('shape'); setMenu(menu === 'shapes' ? null : 'shapes'); }} className={btn(activeTool === 'shape')}>
              {(() => { const I = SHAPES.find((s) => s.kind === shapeKind)!.Icon; return <I size={18} strokeWidth={1.7} />; })()}
            </button>
            {menu === 'shapes' && (
              <Popover pos={popPos}>
                <div className="flex items-center gap-1.5">
                  {SHAPES.map(({ kind, Icon, label }) => (
                    <button key={kind} title={label} aria-label={label} aria-pressed={shapeKind === kind}
                      onClick={() => { setShapeKind(kind); setMenu(null); }}
                      className={cn('w-9 h-9 rounded-lg flex items-center justify-center transition-colors', shapeKind === kind ? 'bg-[#1a1a1a] text-white' : 'bg-[#f4f4f4] text-[#1a1a1a] hover:bg-[#eaeaea]')}>
                      <Icon size={18} strokeWidth={1.7} />
                    </button>
                  ))}
                </div>
              </Popover>
            )}
          </div>

          <button title="Ruler / scale" aria-label="ruler" aria-pressed={activeTool === 'ruler'} onClick={() => setActiveTool('ruler')} className={btn(activeTool === 'ruler')}>
            <Ruler size={18} strokeWidth={1.7} />
          </button>

          <Sep />

          <button onClick={undo} disabled={!canUndo} title="Undo (Cmd/Ctrl+Z)" aria-label="Undo"
            className={cn('w-9 h-9 rounded-full flex items-center justify-center text-[#1a1a1a] transition-colors flex-shrink-0', canUndo ? 'hover:bg-[#f4f4f4]' : 'opacity-30 cursor-not-allowed')}>
            <Undo2 size={18} strokeWidth={1.7} />
          </button>
          <button onClick={redo} disabled={!canRedo} title="Redo (Cmd/Ctrl+Shift+Z)" aria-label="Redo"
            className={cn('w-9 h-9 rounded-full flex items-center justify-center text-[#1a1a1a] transition-colors flex-shrink-0', canRedo ? 'hover:bg-[#f4f4f4]' : 'opacity-30 cursor-not-allowed')}>
            <Redo2 size={18} strokeWidth={1.7} />
          </button>

          <Sep />

          {/* Colour + width */}
          <div className="relative flex-shrink-0">
            <button title="Colour & thickness" aria-label="Colour and thickness" aria-expanded={menu === 'color'}
              onClick={() => setMenu(menu === 'color' ? null : 'color')}
              className="w-9 h-9 rounded-full flex items-center justify-center hover:bg-[#f4f4f4] transition-colors">
              <span className="w-[18px] h-[18px] rounded-full" style={{ background: strokeColor, border: '2px solid #fff', boxShadow: '0 0 0 1.5px #9a9a9a' }} />
            </button>
            {menu === 'color' && (
              <Popover pos={popPos}>
                <div className="w-[200px]">
                  {/* Preset swatches + full colour-wheel picker */}
                  <div className="text-[10px] tracking-widest uppercase text-[#9a9a9a] mb-2">Colour</div>
                  <div className="flex items-center gap-2 flex-wrap">
                    {COLORS.map((c) => (
                      <button key={c} onClick={() => setStrokeColor(c)} aria-label={`Colour ${c}`} aria-pressed={strokeColor === c}
                        className={cn('w-6 h-6 rounded-full transition-transform', strokeColor === c ? 'scale-110 ring-2 ring-offset-2 ring-[#1a1a1a]' : 'hover:scale-105')}
                        style={{ background: c, boxShadow: '0 0 0 1.5px #9a9a9a' }} />
                    ))}
                    {/* Native colour wheel / picker */}
                    <label
                      className="relative w-6 h-6 rounded-full cursor-pointer overflow-hidden"
                      title="Custom colour"
                      style={{ boxShadow: '0 0 0 1.5px #9a9a9a', background: 'conic-gradient(red, yellow, lime, aqua, blue, magenta, red)' }}
                    >
                      <input
                        type="color"
                        value={strokeColor}
                        onChange={(e) => setStrokeColor(e.target.value)}
                        aria-label="Custom colour picker"
                        className="absolute inset-0 opacity-0 cursor-pointer"
                      />
                    </label>
                  </div>

                  <div className="h-[1px] bg-[#eaeaea] my-3" />

                  {/* Size slider with live preview */}
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[10px] tracking-widest uppercase text-[#9a9a9a]">Size</span>
                    <span className="text-[11px] font-semibold text-[#1a1a1a]">{strokeWidth}px</span>
                  </div>
                  <div className="flex items-center gap-2.5">
                    <span className="rounded-full bg-[#1a1a1a] flex-shrink-0" style={{ width: Math.min(strokeWidth, 20) + 2, height: Math.min(strokeWidth, 20) + 2 }} />
                    <input
                      type="range" min={1} max={30} value={strokeWidth}
                      onChange={(e) => setStrokeWidth(Number(e.target.value))}
                      aria-label="Stroke size"
                      className="flex-1 accent-[#1a1a1a]"
                    />
                  </div>
                </div>
              </Popover>
            )}
          </div>

          {/* Check */}
          <button onClick={onCheckWork} aria-label="Check my work"
            className={cn('bg-[#1a1a1a] text-white rounded-[20px] text-xs font-semibold flex items-center justify-center gap-[6px] hover:opacity-80 transition-opacity flex-shrink-0',
              vertical ? 'w-9 h-9 rounded-full' : 'ml-1 px-4 py-[9px]')}>
            <CheckCircle2 size={16} strokeWidth={1.8} />
            {!vertical && 'Check'}
          </button>

          {/* Collapse */}
          <button onClick={toggleToolbarCollapsed} title="Collapse toolbar" aria-label="Collapse toolbar"
            className="w-7 h-9 flex items-center justify-center text-[#9a9a9a] hover:text-[#1a1a1a] transition-colors flex-shrink-0">
            <ChevronDown size={16} strokeWidth={1.8} className={vertical ? '-rotate-90' : ''} />
          </button>
        </>
      )}
    </div>
  );
}

function Popover({ pos, children }: { pos: string; children: React.ReactNode }) {
  return (
    <div className={cn('absolute z-30 bg-white border border-[#9a9a9a] rounded-xl p-3', pos)} style={{ boxShadow: '0 4px 16px rgba(0,0,0,0.14)' }} role="menu">
      {children}
    </div>
  );
}

function MenuItem({ active, icon, label, onClick }: { active?: boolean; icon: React.ReactNode; label: string; onClick: () => void }) {
  return (
    <button onClick={onClick} aria-pressed={active}
      className={cn('w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-[12.5px] whitespace-nowrap transition-colors', active ? 'bg-[#1a1a1a] text-white' : 'text-[#1a1a1a] hover:bg-[#f4f4f4]')}>
      {icon} {label}
    </button>
  );
}
