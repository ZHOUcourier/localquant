import React from 'react';
import { cn } from '@/lib/utils';

export type BadgeVariant = 'default' | 'success' | 'warning' | 'error' | 'info';

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

const variantStyles: Record<BadgeVariant, string> = {
  default: 'bg-[#302c2c] text-[#9a9898] border-[#403b3b]',
  success: 'bg-[#30d158]/10 text-[#30d158] border-[#30d158]/30',
  warning: 'bg-[#ff9f0a]/10 text-[#ff9f0a] border-[#ff9f0a]/30',
  error: 'bg-[#ff3b30]/10 text-[#ff3b30] border-[#ff3b30]/30',
  info: 'bg-[#64d2ff]/10 text-[#64d2ff] border-[#64d2ff]/30',
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
