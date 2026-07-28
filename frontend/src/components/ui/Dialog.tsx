import React, { useEffect } from 'react';
import { cn } from '@/lib/utils';

export interface DialogProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'title'> {
  open: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  footer?: React.ReactNode;
}

export const Dialog = React.forwardRef<HTMLDivElement, DialogProps>(
  ({ open, onClose, title, footer, children, className, ...props }, ref) => {
    useEffect(() => {
      if (!open) return;
      const handleEsc = (e: KeyboardEvent) => {
        if (e.key === 'Escape') onClose();
      };
      document.addEventListener('keydown', handleEsc);
      return () => document.removeEventListener('keydown', handleEsc);
    }, [open, onClose]);

    if (!open) return null;

    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center">
        <div
          className="absolute inset-0 bg-black/40"
          onClick={onClose}
        />
        <div
          ref={ref}
          className={cn(
            'relative z-10 min-w-[320px] max-w-[560px] rounded-[4px] border bg-[#fdfcfc]',
            className
          )}
          style={{ borderColor: 'rgba(15, 0, 0, 0.12)' }}
          {...props}
        >
          {title && (
            <div
              className="flex items-center justify-between px-4 py-3"
              style={{ borderBottom: '1px solid rgba(15, 0, 0, 0.12)' }}
            >
              <div className="text-sm font-medium text-[#201d1d]">{title}</div>
              <button
                type="button"
                className="text-[#9a9898] hover:text-[#201d1d] transition-colors cursor-pointer"
                onClick={onClose}
              >
                ✕
              </button>
            </div>
          )}
          <div className="px-4 py-3 text-sm text-[#201d1d]">{children}</div>
          {footer && (
            <div
              className="flex items-center justify-end gap-2 px-4 py-3"
              style={{ borderTop: '1px solid rgba(15, 0, 0, 0.12)' }}
            >
              {footer}
            </div>
          )}
        </div>
      </div>
    );
  }
);
Dialog.displayName = 'Dialog';
