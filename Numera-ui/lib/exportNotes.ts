/**
 * exportNotesPDF — turns a session into a clean, formatted PDF "revision notes"
 * page: header, the question, the student's canvas working (Konva PNG snapshot),
 * and the key tutor discussion. Pure client-side via jsPDF.
 */
import { jsPDF } from 'jspdf';
import type { TranscriptMessage } from '@/store/useNumeraStore';

interface NotesData {
  questionNumber: number;
  questionText: string;
  canvasPng: string | null; // data URL from konva toDataURL
  transcript: TranscriptMessage[];
}

const INK = 26;
const GREY = 122;

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = src;
  });
}

export async function exportNotesPDF({
  questionNumber,
  questionText,
  canvasPng,
  transcript,
}: NotesData): Promise<void> {
  const doc = new jsPDF({ unit: 'pt', format: 'a4' });
  const W = doc.internal.pageSize.getWidth();
  const H = doc.internal.pageSize.getHeight();
  const M = 48;
  const contentW = W - M * 2;
  let y = M;

  const newPageIfNeeded = (needed: number) => {
    if (y + needed > H - M) { doc.addPage(); y = M; }
  };

  // ── Header ──
  doc.setFont('helvetica', 'bold'); doc.setFontSize(20); doc.setTextColor(INK);
  doc.text('Numera — Revision Notes', M, y);
  y += 16;
  doc.setFont('helvetica', 'normal'); doc.setFontSize(9); doc.setTextColor(GREY);
  const date = new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
  doc.text(`Nablix  ·  ${date}`, M, y);
  y += 12;
  doc.setDrawColor(200); doc.setLineWidth(1); doc.line(M, y, W - M, y);
  y += 28;

  // ── Question ──
  doc.setFont('helvetica', 'bold'); doc.setFontSize(10); doc.setTextColor(GREY);
  doc.text(`QUESTION ${questionNumber}`, M, y);
  y += 18;
  doc.setFont('helvetica', 'bold'); doc.setFontSize(15); doc.setTextColor(INK);
  doc.text(`Solve for x:   ${questionText}`, M, y);
  y += 26;

  // ── Working (canvas snapshot) ──
  doc.setFont('helvetica', 'bold'); doc.setFontSize(10); doc.setTextColor(GREY);
  doc.text('YOUR WORKING', M, y);
  y += 12;
  if (canvasPng) {
    try {
      const img = await loadImage(canvasPng);
      const ratio = img.naturalHeight / img.naturalWidth || 0.5;
      let imgW = contentW;
      let imgH = imgW * ratio;
      const maxH = 320;
      if (imgH > maxH) { imgH = maxH; imgW = imgH / ratio; }
      newPageIfNeeded(imgH + 20);
      doc.setDrawColor(220); doc.setLineWidth(1);
      doc.rect(M, y, contentW, imgH);
      doc.addImage(canvasPng, 'PNG', M, y, imgW, imgH, undefined, 'FAST');
      y += imgH + 26;
    } catch {
      doc.setFont('helvetica', 'italic'); doc.setFontSize(10); doc.setTextColor(150);
      doc.text('Working could not be captured.', M, y); y += 24;
    }
  } else {
    doc.setFont('helvetica', 'italic'); doc.setFontSize(10); doc.setTextColor(150);
    doc.text('No working on the canvas yet.', M, y); y += 24;
  }

  // ── Tutor discussion ──
  if (transcript.length) {
    newPageIfNeeded(40);
    doc.setFont('helvetica', 'bold'); doc.setFontSize(10); doc.setTextColor(GREY);
    doc.text('TUTOR DISCUSSION', M, y);
    y += 18;
    doc.setFontSize(10);
    for (const m of transcript) {
      const who = m.role === 'ai' ? 'Numera' : 'You';
      const lines = doc.splitTextToSize(m.text, contentW - 52) as string[];
      newPageIfNeeded(lines.length * 13 + 8);
      doc.setFont('helvetica', 'bold'); doc.setTextColor(m.role === 'ai' ? INK : 90);
      doc.text(`${who}:`, M, y);
      doc.setFont('helvetica', 'normal'); doc.setTextColor(45);
      doc.text(lines, M + 52, y);
      y += Math.max(14, lines.length * 13) + 6;
    }
  }

  doc.save(`numera-notes-q${questionNumber}.pdf`);
}
