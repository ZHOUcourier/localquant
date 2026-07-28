import React from 'react';
import { cn } from '@/lib/utils';

export type BadgeVariant = 'default' | 'success' | 'warning' | 'error' | 'info';

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

const variantStyles: Record<BadgeVariant, string> = {
  default: 'bg-[#21262d] text-[#808080] border-[#30363d]',
  success: 'bg-[#7fd88f]/10 text-[#7fd88f] border-[#7fd88f]/30',
  warning: 'bg-[#f5a742]/10 text-[#f5a742] border-[#f5a742]/30',
  error: 'bg-[#e06c75]/10 text-[#e06c75] border-[#e06c75]/30',
  info: 'bg-[#56b6c2]/10 text-[#56b6c2] border-[#56b6c2]/30',
};

export const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant = 'default', children, ...props }, ref) => {
    return (
      <span
        ref={ref}
        className={cn(
          'inline-flex items-center rounded-[2px] border px-1.5 py-0.5 text-xs font-medium',
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
