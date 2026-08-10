'use client';

import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';

/** Liquid-glass modal sheet with scrim, focus trap and Esc-to-close (Radix). */
export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="lg-scrim lg-anim-fade fixed inset-0 z-50" />
        <Dialog.Content className="lg-sheet lg-anim-pop fixed left-1/2 top-1/2 z-50 w-[92vw] max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-card p-0 focus:outline-none">
          <div className="flex items-start justify-between gap-3 border-b border-white/50 px-5 py-4">
            <div>
              <Dialog.Title className="font-display text-base font-bold text-focus-navy">{title}</Dialog.Title>
              {description && <Dialog.Description className="mt-0.5 text-xs text-slate-blue">{description}</Dialog.Description>}
            </div>
            <Dialog.Close className="flex h-7 w-7 items-center justify-center rounded-lg text-slate-blue hover:bg-white/60">
              <X className="h-4 w-4" />
            </Dialog.Close>
          </div>
          <div className="lg-scroll max-h-[70vh] overflow-y-auto px-5 py-4">{children}</div>
          {footer && <div className="flex items-center justify-end gap-2 border-t border-white/50 px-5 py-3">{footer}</div>}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
