'use client';

/**
 * Nablix Assist — consented, masked screenshots.
 *
 * The canvas exporter only captures the Konva drawing surface; support needs
 * the whole app view, which requires a DOM screenshot (html2canvas).
 *
 * PRIVACY RULES (rule 3):
 *  - capture only happens after the student consents in the EscalationPanel;
 *  - sensitive fields (passwords, OTPs, emails, phones, payment-like inputs and
 *    anything tagged data-support-mask) are masked in the CLONED document that
 *    html2canvas renders — the live page is never touched;
 *  - the image goes straight to the support endpoint and is never stored
 *    client-side.
 */

import html2canvas from 'html2canvas';

// Fields whose values must never appear in a screenshot.
const SENSITIVE_SELECTOR = [
  'input[type="password"]',
  'input[inputmode="numeric"]', // OTP codes
  'input[type="email"]',
  'input[type="tel"]',
  'input[autocomplete*="cc-"]', // payment
  '[data-support-mask]',
].join(', ');

const MASK = '••••••';

function maskSensitiveFields(clonedDoc: Document): void {
  clonedDoc.querySelectorAll<HTMLElement>(SENSITIVE_SELECTOR).forEach((el) => {
    if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
      if (el.value) el.value = MASK;
      if (el.placeholder) el.placeholder = '';
    } else {
      el.textContent = MASK;
    }
  });
}

/**
 * Capture the Nablix app area with sensitive fields masked. Returns a PNG data
 * URL for immediate upload — callers must not persist it.
 */
export async function captureMaskedScreenshot(): Promise<string> {
  const canvas = await html2canvas(document.body, {
    logging: false,
    // Konva/WebGL layers need their current framebuffer read back.
    useCORS: true,
    onclone: maskSensitiveFields,
  });
  return canvas.toDataURL('image/png');
}
