'use client';

/**
 * DrawingCanvas — react-konva powered drawing surface
 *
 * Tools:
 *   - pen / pencil: freehand (pencil is lighter & thinner)
 *   - eraser:       freehand rub (stroke mode) OR tap-to-delete (object mode)
 *   - shape:        rectangle / circle / triangle (drag to size)
 *   - ruler:        straight line (scale)
 *
 * Committed items + undo/redo history live in the Zustand store, so the
 * floating toolbar's Undo/Redo buttons and Cmd/Ctrl+Z share one source of
 * truth. exportPNG() is exposed via ref for "Check My Work" submissions.
 */

import { useRef, useState, useCallback, useEffect } from 'react';
import { Stage, Layer, Line, Rect, Ellipse, Group, Text } from 'react-konva';
import type Konva from 'konva';
import { useNumeraStore, type DrawnItem } from '@/store/useNumeraStore';
import { uid } from '@/lib/uid';
import TutorLayer from './TutorLayer';
import TutorMathOverlay from './TutorMathOverlay';

interface DrawingCanvasProps {
  onExportReady?: (exportFn: () => string | null) => void;
}

export default function DrawingCanvas({ onExportReady }: DrawingCanvasProps) {
  const stageRef = useRef<Konva.Stage>(null);
  const isDrawing = useRef(false);
  const startPos = useRef<{ x: number; y: number } | null>(null);

  const {
    activeTool, shapeKind, eraserMode, strokeColor, strokeWidth,
    items, remoteItems, addItem, removeItem, undo, redo,
  } = useNumeraStore();

  const [draft, setDraft] = useState<DrawnItem | null>(null);
  const draftRef = useRef<DrawnItem | null>(null);
  const [containerSize, setContainerSize] = useState({ width: 800, height: 600 });
  const containerRef = useRef<HTMLDivElement>(null);

  const setDraftItem = useCallback((item: DrawnItem | null) => {
    draftRef.current = item;
    setDraft(item);
  }, []);

  const objectErase = activeTool === 'eraser' && eraserMode === 'object';

  // ── Resize observer ──────────────────────────────────────────────────────────
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) {
        setContainerSize({ width: e.contentRect.width, height: e.contentRect.height });
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // ── Expose exportPNG to parent ───────────────────────────────────────────────
  useEffect(() => {
    onExportReady?.(() => {
      if (!stageRef.current) return null;
      return stageRef.current.toDataURL({ mimeType: 'image/png', pixelRatio: 2 });
    });
  }, [onExportReady]);

  // ── Pointer handlers ─────────────────────────────────────────────────────────
  const handleDown = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) => {
      // Object-eraser deletes via clicking a shape, not by drawing.
      if (activeTool === 'eraser' && eraserMode === 'object') return;
      const pos = e.target.getStage()?.getPointerPosition();
      if (!pos) return;
      isDrawing.current = true;
      startPos.current = { x: pos.x, y: pos.y };
      const id = uid();

      if (activeTool === 'pen' || activeTool === 'pencil' || activeTool === 'highlighter' || activeTool === 'eraser') {
        const isEraser = activeTool === 'eraser';
        const size =
          isEraser ? strokeWidth * 6
          : activeTool === 'highlighter' ? strokeWidth * 5
          : activeTool === 'pencil' ? Math.max(1, strokeWidth - 1)
          : strokeWidth;
        setDraftItem({
          id,
          kind: 'stroke',
          tool: activeTool,
          points: [pos.x, pos.y],
          color: isEraser ? '#ffffff' : strokeColor,
          size,
        });
      } else if (activeTool === 'ruler') {
        setDraftItem({ id, kind: 'line', points: [pos.x, pos.y, pos.x, pos.y], color: strokeColor, size: strokeWidth });
      } else if (activeTool === 'shape') {
        if (shapeKind === 'triangle') {
          setDraftItem({ id, kind: 'triangle', points: [pos.x, pos.y, pos.x, pos.y, pos.x, pos.y], color: strokeColor, size: strokeWidth });
        } else if (shapeKind === 'circle') {
          setDraftItem({ id, kind: 'ellipse', x: pos.x, y: pos.y, w: 0, h: 0, color: strokeColor, size: strokeWidth });
        } else {
          setDraftItem({ id, kind: 'rect', x: pos.x, y: pos.y, w: 0, h: 0, color: strokeColor, size: strokeWidth });
        }
      }
    },
    [activeTool, eraserMode, shapeKind, strokeColor, strokeWidth, setDraftItem]
  );

  const handleMove = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) => {
      if (!isDrawing.current) return;
      const pos = e.target.getStage()?.getPointerPosition();
      const start = startPos.current;
      const prev = draftRef.current;
      if (!pos || !start || !prev) return;

      if (prev.kind === 'stroke') {
        setDraftItem({ ...prev, points: [...prev.points, pos.x, pos.y] });
      } else if (prev.kind === 'line') {
        setDraftItem({ ...prev, points: [start.x, start.y, pos.x, pos.y] });
      } else if (prev.kind === 'triangle') {
        const left = Math.min(start.x, pos.x), right = Math.max(start.x, pos.x);
        const top = Math.min(start.y, pos.y), bottom = Math.max(start.y, pos.y);
        setDraftItem({ ...prev, points: [(left + right) / 2, top, left, bottom, right, bottom] });
      } else {
        // rect / ellipse
        setDraftItem({
          ...prev,
          x: Math.min(start.x, pos.x),
          y: Math.min(start.y, pos.y),
          w: Math.abs(pos.x - start.x),
          h: Math.abs(pos.y - start.y),
        });
      }
    },
    [setDraftItem]
  );

  const handleUp = useCallback(() => {
    if (!isDrawing.current) return;
    isDrawing.current = false;
    startPos.current = null;
    const item = draftRef.current;
    if (item) {
      // Discard zero-size shapes / single-point taps so undo isn't cluttered
      let meaningful = false;
      if (item.kind === 'stroke') meaningful = item.points.length > 2;
      else if (item.kind === 'line') meaningful = item.points[0] !== item.points[2] || item.points[1] !== item.points[3];
      else if (item.kind === 'triangle') meaningful = (item.points[4] - item.points[2]) > 2 && (item.points[3] - item.points[1]) > 2;
      else meaningful = item.w > 2 && item.h > 2; // rect / ellipse
      if (meaningful) addItem(item);
    }
    setDraftItem(null);
  }, [addItem, setDraftItem]);

  // ── Dev-only hook to exercise the tutor layer before the backend exists ──────
  useEffect(() => {
    if (process.env.NODE_ENV === 'production') return;
    (window as unknown as Record<string, unknown>).numeraTutor = {
      draw: (p: Parameters<ReturnType<typeof useNumeraStore.getState>['applyCanvasDraw']>[0]) =>
        useNumeraStore.getState().applyCanvasDraw(p),
      clear: () => useNumeraStore.getState().clearTutorMarks(),
    };
  }, []);

  // ── Undo / Redo via keyboard (shares store history with toolbar) ─────────────
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const meta = e.metaKey || e.ctrlKey;
      if (!meta) return;
      if (e.key === 'z' && !e.shiftKey) { e.preventDefault(); undo(); }
      else if (e.key === 'y' || (e.key === 'z' && e.shiftKey)) { e.preventDefault(); redo(); }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [undo, redo]);

  // `deletable` items respond to the object-eraser (tap to delete).
  const renderItem = (item: DrawnItem, deletable = false) => {
    const onSelect = deletable && objectErase ? () => removeItem(item.id) : undefined;
    const hit = onSelect ? Math.max(item.kind === 'stroke' ? item.size : item.size, 16) : undefined;
    const common = { onClick: onSelect, onTap: onSelect, hitStrokeWidth: hit };

    if (item.kind === 'rect') {
      return <Rect key={item.id} x={item.x} y={item.y} width={item.w} height={item.h}
        stroke={item.color} strokeWidth={item.size} cornerRadius={3}
        fill={onSelect ? 'rgba(0,0,0,0.001)' : undefined} {...common} />;
    }
    if (item.kind === 'ellipse') {
      return <Ellipse key={item.id} x={item.x + item.w / 2} y={item.y + item.h / 2}
        radiusX={item.w / 2} radiusY={item.h / 2} stroke={item.color} strokeWidth={item.size}
        fill={onSelect ? 'rgba(0,0,0,0.001)' : undefined} {...common} />;
    }
    if (item.kind === 'line') {
      // Ruler / scale — line + tick marks + a live length readout
      const [x1, y1, x2, y2] = item.points;
      const dx = x2 - x1, dy = y2 - y1;
      const len = Math.hypot(dx, dy) || 1;
      const ux = dx / len, uy = dy / len;   // along
      const nx = -uy, ny = ux;               // normal
      const ticks = [];
      for (let d = 0; d <= len; d += 20) {
        const tl = d % 100 === 0 ? 9 : 5;
        const px = x1 + ux * d, py = y1 + uy * d;
        ticks.push(<Line key={d} points={[px, py, px + nx * tl, py + ny * tl]} stroke={item.color} strokeWidth={1} />);
      }
      return (
        <Group key={item.id} onClick={onSelect} onTap={onSelect}>
          <Line points={[x1, y1, x2, y2]} stroke={item.color} strokeWidth={Math.max(item.size, 1.5)} lineCap="round" hitStrokeWidth={onSelect ? 16 : undefined} />
          {ticks}
          {len >= 8 && (
            <Text x={(x1 + x2) / 2 + nx * 16 - 16} y={(y1 + y2) / 2 + ny * 16 - 6} text={`${Math.round(len)} px`} fontSize={11} fill={item.color} />
          )}
        </Group>
      );
    }
    // stroke / line / triangle → Line
    const isPencil = item.kind === 'stroke' && item.tool === 'pencil';
    const isHighlighter = item.kind === 'stroke' && item.tool === 'highlighter';
    const isEraser = item.kind === 'stroke' && item.tool === 'eraser';
    return (
      <Line
        key={item.id}
        points={item.points}
        stroke={item.color}
        strokeWidth={item.size}
        opacity={isHighlighter ? 0.35 : isPencil ? 0.55 : 1}
        tension={item.kind === 'stroke' ? 0.5 : 0}
        closed={item.kind === 'triangle'}
        lineCap={isHighlighter ? 'butt' : 'round'}
        lineJoin="round"
        globalCompositeOperation={
          isEraser ? 'destination-out' : isHighlighter ? 'multiply' : 'source-over'
        }
        {...common}
      />
    );
  };

  const cursor =
    activeTool === 'eraser' ? (eraserMode === 'object' ? 'pointer' : 'cell')
    : (activeTool === 'pen' || activeTool === 'pencil' || activeTool === 'highlighter') ? 'crosshair'
    : 'copy';

  return (
    <div ref={containerRef} className="w-full h-full relative" aria-label="Drawing canvas">
      <Stage
        ref={stageRef}
        width={containerSize.width}
        height={containerSize.height}
        onMouseDown={handleDown}
        onMouseMove={handleMove}
        onMouseUp={handleUp}
        onTouchStart={handleDown}
        onTouchMove={handleMove}
        onTouchEnd={handleUp}
        style={{ cursor }}
      >
        <Layer>
          {remoteItems.map((it) => renderItem(it))}
          {items.map((it) => renderItem(it, true))}
          {draft && renderItem(draft)}
        </Layer>
        {/* AI-tutor marks — separate, non-erasable layer above the student's */}
        <TutorLayer width={containerSize.width} height={containerSize.height} />
      </Stage>
      {/* Tutor maths as real KaTeX, overlaid on the same coordinate space */}
      <TutorMathOverlay width={containerSize.width} height={containerSize.height} />
    </div>
  );
}
