import React from 'react';
import { cn } from '@/lib/utils';

export interface CardProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'title'> {
  title?: React.ReactNode;
  extra?: React.ReactNode;
}

export const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, title, extra, children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          'rounded-[4px] border bg-[#f1eeee]',
          className
        )}
        style={{ borderColor: 'rgba(15, 0, 0, 0.12)' }}
        {...props}
      >
        {(title || extra) && (
          <div className="flex items-center justify-between px-3 py-2" style={{ borderBottom: '1px solid rgba(15, 0, 0, 0.12)' }}>
            {title && (
              <div className="text-sm font-medium text-[#201d1d]">{title}</div>
            )}
            {extra && <div className="flex items-center gap-2">{extra}</div>}
          </div>
        )}
        <div className="p-3">{children}</div>
      </div>
    );
  }
);
Card.displayName = 'Card';
