import React from 'react';
import { cn } from '@/lib/utils';

export type BadgeVariant = 'default' | 'success' | 'warning' | 'error' | 'info';

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

const variantStyles: Record<BadgeVariant, string> = {
  default: 'bg-[#f8f7f7] text-[#646262] border-[rgba(15,0,0,0.12)]',
  success: 'bg-[#30d158]/15 text-[#30d158] border-[#30d158]/30',
  warning: 'bg-[#ff9f0a]/15 text-[#cc7f08] border-[#ff9f0a]/30',
  error: 'bg-[#ff3b30]/15 text-[#d70015] border-[#ff3b30]/30',
  info: 'bg-[#007aff]/15 text-[#0056b3] border-[#007aff]/30',
};

export const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant = 'default', children, ...props }, ref) => {
    return (
      <span
        ref={ref}
        className={cn(
          'inline-flex items-center rounded-[4px] border px-1.5 py-0.5 text-xs font-medium',
          variantStyles[variant],
          className
        )}
        {...props}
      >
        {children}
      </span>
    );
  }
);
Badge.displayName = 'Badge';
