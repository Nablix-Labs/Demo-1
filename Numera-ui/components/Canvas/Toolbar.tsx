'use client';

import { useEffect, useRef, useState } from 'react';
import {
  Pen, Pencil, Highlighter, Eraser, Ruler, Square, Circle, Triangle,
  Undo2, Redo2, CheckCircle2, Trash2, MousePointerClick, Brush, Sparkles,
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

// Smooth, Apple-ish expand/collapse. easeOutExpo-like: fast out, gentle settle.
const EASE = 'cubic-bezier(0.22, 1, 0.36, 1)';
const OPEN_MS = 420;
const DRAG_THRESHOLD = 4; // px before a press on the head counts as a drag, not a tap

export default function Toolbar({ onCheckWork }: ToolbarProps) {
  const {
    activeTool, shapeKind, eraserMode, strokeColor, strokeWidth, items, undone,
    setActiveTool, setShapeKind, setEraserMode, setStrokeColor, setStrokeWidth,
    undo, redo, clearCanvas, clearTutorMarks,
    toolbarPos, setToolbarPos, toolbarCollapsed, toggleToolbarCollapsed,
    toolbarOrientation, setToolbarOrientation,
  } = useNumeraStore();

  const [menu, setMenu] = useState<'color' | 'shapes' | 'eraser' | null>(null);
  const [dragging, setDragging] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const dragOffset = useRef<{ dx: number; dy: number } | null>(null);
  const dragStart = useRef<{ x: number; y: number } | null>(null);
  const didDrag = useRef(false);

  const vertical = toolbarOrientation === 'vertical';
  // Shrunk = shown as the small puck: either the user collapsed it, or it's
  // mid-drag (collapse while moving, expand once dropped — Apple-style).
  const shrunk = toolbarCollapsed || dragging;

  // Overflow must be hidden while the bar animates open/closed (so tools clip
  // cleanly), but visible once open so the colour/eraser popovers aren't cut off.
  const [overflowVisible, setOverflowVisible] = useState(!toolbarCollapsed);
  useEffect(() => {
    if (shrunk) { setOverflowVisible(false); setMenu(null); return; }
    const t = setTimeout(() => setOverflowVisible(true), OPEN_MS);
    return () => clearTimeout(t);
  }, [shrunk]);

  // Close any open popover on outside click / Escape
  useEffect(() => {
    if (!menu) return;
    const onDoc = (e: MouseEvent) => { if (rootRef.current && !rootRef.current.contains(e.target as Node)) setMenu(null); };
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setMenu(null);
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey); };
  }, [menu]);

  // ── Drag from the head — move the palette; rotate to vertical when docked ─────
  const onHeadDown = (e: React.PointerEvent) => {
    const el = rootRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    dragOffset.current = { dx: e.clientX - r.left, dy: e.clientY - r.top };
    dragStart.current = { x: e.clientX, y: e.clientY };
    didDrag.current = false;
    el.setPointerCapture(e.pointerId);
    e.preventDefault();
    e.stopPropagation();
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragOffset.current) return;
    const el = rootRef.current;
    const parent = el?.offsetParent as HTMLElement | null;
    if (!el || !parent) return;
    // Only treat it as a drag once past the threshold, so a plain tap toggles.
    if (!didDrag.current && dragStart.current) {
      if (Math.abs(e.clientX - dragStart.current.x) > DRAG_THRESHOLD ||
          Math.abs(e.clientY - dragStart.current.y) > DRAG_THRESHOLD) {
        didDrag.current = true;
        setDragging(true); // shrink to the puck while moving
      }
    }
    if (!didDrag.current) return;
    const pr = parent.getBoundingClientRect();
    const w = el.offsetWidth, h = el.offsetHeight;
    const x = Math.max(8, Math.min(e.clientX - pr.left - dragOffset.current.dx, pr.width - w - 8));
    const y = Math.max(8, Math.min(e.clientY - pr.top - dragOffset.current.dy, pr.height - h - 8));
    setToolbarPos({ x, y });
    const o = (x <= 24 || x >= pr.width - w - 24) ? 'vertical' : 'horizontal';
    if (o !== toolbarOrientation) setToolbarOrientation(o);
  };
  const onPointerUp = (e: React.PointerEvent) => {
    dragOffset.current = null;
    dragStart.current = null;
    setDragging(false); // dropped → expand back (unless the user had it collapsed)
    try { rootRef.current?.releasePointerCapture(e.pointerId); } catch { /* noop */ }
  };
  // Tap on the head (no drag) toggles collapse.
  const onHeadClick = () => {
    if (didDrag.current) { didDrag.current = false; return; }
    toggleToolbarCollapsed();
  };

  const positioned = toolbarPos != null;
  const canUndo = items.length > 0;
  const canRedo = undone.length > 0;

  const Sep = () => <div className={cn('bg-muted-gray flex-shrink-0', vertical ? 'h-[1.5px] w-[22px] my-0.5' : 'w-[1.5px] h-[22px] mx-0.5')} />;
  const btn = (active: boolean) =>
    cn('w-9 h-9 rounded-full flex items-center justify-center transition-colors flex-shrink-0',
      active ? 'bg-focus-navy text-white' : 'bg-transparent text-ink hover:bg-reading-surface');
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
        'lg-glass absolute z-20 flex items-center rounded-full select-none',
        vertical ? 'flex-col' : 'flex-row',
        'p-1.5',
        !positioned && 'bottom-16 left-1/2 -translate-x-1/2'
      )}
      style={{ transition: `box-shadow ${OPEN_MS}ms ${EASE}`, ...(positioned ? { left: toolbarPos!.x, top: toolbarPos!.y } : {}) }}
      role="toolbar"
      aria-label="Drawing tools"
    >
      {/* Head — active tool. Drag to move, tap to expand/collapse (Apple-style). */}
      <button
        onPointerDown={onHeadDown}
        onClick={onHeadClick}
        title={toolbarCollapsed ? 'Tap to open tools · drag to move' : 'Collapse tools · drag to move'}
        aria-label={toolbarCollapsed ? 'Open tools' : 'Collapse tools'}
        aria-expanded={!toolbarCollapsed}
        className={cn(
          'w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 touch-none cursor-grab active:cursor-grabbing transition-colors',
          shrunk ? 'text-focus-navy' : 'text-ink hover:bg-reading-surface'
        )}
      >
        <ActiveToolIcon size={18} strokeWidth={1.7} />
      </button>

      {/* Expandable region — grid 0fr↔1fr animates smoothly to content size. */}
      <div
        className="grid"
        aria-hidden={shrunk}
        style={{
          gridTemplateColumns: vertical ? undefined : (shrunk ? '0fr' : '1fr'),
          gridTemplateRows: vertical ? (shrunk ? '0fr' : '1fr') : undefined,
          opacity: shrunk ? 0 : 1,
          transition: `grid-template-columns ${OPEN_MS}ms ${EASE}, grid-template-rows ${OPEN_MS}ms ${EASE}, opacity ${Math.round(OPEN_MS * 0.7)}ms ease`,
        }}
      >
        <div className="min-w-0 min-h-0" style={{ overflow: overflowVisible ? 'visible' : 'hidden' }}>
          <div className={cn('flex items-center gap-[5px]', vertical ? 'flex-col pt-1' : 'flex-row pl-1')}>
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
                  <div className="h-[1px] bg-muted-gray my-1" />
                  <MenuItem icon={<Trash2 size={15} strokeWidth={1.7} />} label="Clear my writing" onClick={() => { clearCanvas(); setMenu(null); }} />
                  <MenuItem icon={<Sparkles size={15} strokeWidth={1.7} />} label="Clear tutor writing" onClick={() => { clearTutorMarks(); setMenu(null); }} />
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
                        className={cn('w-9 h-9 rounded-lg flex items-center justify-center transition-colors', shapeKind === kind ? 'bg-focus-navy text-white' : 'bg-reading-surface text-ink hover:bg-muted-gray')}>
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
              className={cn('w-9 h-9 rounded-full flex items-center justify-center text-ink transition-colors flex-shrink-0', canUndo ? 'hover:bg-reading-surface' : 'opacity-30 cursor-not-allowed')}>
              <Undo2 size={18} strokeWidth={1.7} />
            </button>
            <button onClick={redo} disabled={!canRedo} title="Redo (Cmd/Ctrl+Shift+Z)" aria-label="Redo"
              className={cn('w-9 h-9 rounded-full flex items-center justify-center text-ink transition-colors flex-shrink-0', canRedo ? 'hover:bg-reading-surface' : 'opacity-30 cursor-not-allowed')}>
              <Redo2 size={18} strokeWidth={1.7} />
            </button>

            <Sep />

            {/* Colour + width */}
            <div className="relative flex-shrink-0">
              <button title="Colour & thickness" aria-label="Colour and thickness" aria-expanded={menu === 'color'}
                onClick={() => setMenu(menu === 'color' ? null : 'color')}
                className="w-9 h-9 rounded-full flex items-center justify-center hover:bg-reading-surface transition-colors">
                <span className="w-[18px] h-[18px] rounded-full" style={{ background: strokeColor, border: '2px solid #fff', boxShadow: '0 0 0 1.5px #E0E2E5' }} />
              </button>
              {menu === 'color' && (
                <Popover pos={popPos}>
                  <div className="w-[200px]">
                    <div className="text-[10px] tracking-widest uppercase text-slate-blue mb-2">Colour</div>
                    <div className="flex items-center gap-2 flex-wrap">
                      {COLORS.map((c) => (
                        <button key={c} onClick={() => setStrokeColor(c)} aria-label={`Colour ${c}`} aria-pressed={strokeColor === c}
                          className={cn('w-6 h-6 rounded-full transition-transform', strokeColor === c ? 'scale-110 ring-2 ring-offset-2 ring-focus-navy' : 'hover:scale-105')}
                          style={{ background: c, boxShadow: '0 0 0 1.5px #E0E2E5' }} />
                      ))}
                      <label
                        className="relative w-6 h-6 rounded-full cursor-pointer overflow-hidden"
                        title="Custom colour"
                        style={{ boxShadow: '0 0 0 1.5px #E0E2E5', background: 'conic-gradient(red, yellow, lime, aqua, blue, magenta, red)' }}
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

                    <div className="h-[1px] bg-muted-gray my-3" />

                    <div className="flex items-center justify-between mb-2">
                      <span className="text-[10px] tracking-widest uppercase text-slate-blue">Size</span>
                      <span className="text-[11px] font-semibold text-ink">{strokeWidth}px</span>
                    </div>
                    <div className="flex items-center gap-2.5">
                      <span className="rounded-full bg-focus-navy flex-shrink-0" style={{ width: Math.min(strokeWidth, 20) + 2, height: Math.min(strokeWidth, 20) + 2 }} />
                      <input
                        type="range" min={1} max={30} value={strokeWidth}
                        onChange={(e) => setStrokeWidth(Number(e.target.value))}
                        aria-label="Stroke size"
                        className="flex-1 accent-focus-navy"
                      />
                    </div>
                  </div>
                </Popover>
              )}
            </div>

            {/* Check */}
            <button onClick={onCheckWork} aria-label="Check my work" data-support-id="check-answer"
              className={cn('bg-highlight-amber text-ink rounded-[20px] text-xs font-semibold flex items-center justify-center gap-[6px] hover:brightness-95 transition-all flex-shrink-0',
                vertical ? 'w-9 h-9 rounded-full' : 'ml-1 mr-0.5 px-4 py-[9px]')}>
              <CheckCircle2 size={16} strokeWidth={1.8} />
              {!vertical && 'Check'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Popover({ pos, children }: { pos: string; children: React.ReactNode }) {
  return (
    <div className={cn('absolute z-30 bg-white border border-muted-gray rounded-xl p-3', pos)} style={{ boxShadow: '0 4px 16px rgba(0,0,0,0.14)' }} role="menu">
      {children}
    </div>
  );
}

function MenuItem({ active, icon, label, onClick }: { active?: boolean; icon: React.ReactNode; label: string; onClick: () => void }) {
  return (
    <button onClick={onClick} aria-pressed={active}
      className={cn('w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-[12.5px] whitespace-nowrap transition-colors', active ? 'bg-focus-navy text-white' : 'text-ink hover:bg-reading-surface')}>
      {icon} {label}
    </button>
  );
}
