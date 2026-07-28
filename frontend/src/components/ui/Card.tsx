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
          'rounded-[4px] border border-[#30363d] bg-[#161b22]',
          className
        )}
        {...props}
      >
        {(title || extra) && (
          <div className="flex items-center justify-between border-b border-[#30363d] px-3 py-2">
            {title && (
              <div className="text-sm font-medium text-[#eeeeee]">{title}</div>
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
