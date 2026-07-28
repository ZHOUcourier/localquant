import React from 'react';
import { cn } from '@/lib/utils';

export interface ScrollAreaProps extends React.HTMLAttributes<HTMLDivElement> {
  maxHeight?: string | number;
  horizontal?: boolean;
}

export const ScrollArea = React.forwardRef<HTMLDivElement, ScrollAreaProps>(
  ({ maxHeight, horizontal = false, children, className, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          'overflow-auto',
          horizontal && 'overflow-x-auto',
          className
        )}
        style={{ maxHeight }}
        {...props}
      >
        {children}
      </div>
    );
  }
);
ScrollArea.displayName = 'ScrollArea';
