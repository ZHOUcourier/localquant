import React from 'react';
import { cn } from '@/lib/utils';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md' | 'lg';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary: 'bg-[#201d1d] text-[#fdfcfc] border-none hover:bg-[#302c2c] disabled:bg-[#f1eeee] disabled:text-[#6e6e73]',
  secondary: 'bg-transparent text-[#201d1d] border border-[#646262] hover:border-[#9a9898] hover:bg-[#f1eeee] disabled:border-[rgba(15,0,0,0.12)] disabled:text-[#6e6e73]',
  ghost: 'bg-transparent text-[#201d1d] border border-transparent hover:bg-[#f1eeee] disabled:text-[#6e6e73]',
  danger: 'bg-[#ff3b30] text-[#fdfcfc] border-none hover:bg-[#d70015] disabled:bg-[#6e6e73] disabled:text-[#fdfcfc]',
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: 'px-2 py-1 text-xs',
  md: 'px-3 py-1.5 text-sm',
  lg: 'px-4 py-2 text-base',
};

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'secondary', size = 'md', loading, disabled, children, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          'inline-flex items-center justify-center rounded-[4px] font-medium transition-colors duration-150 cursor-pointer',
          variantStyles[variant],
          sizeStyles[size],
          (disabled || loading) && 'cursor-not-allowed opacity-70',
          className
        )}
        disabled={disabled || loading}
        {...props}
      >
        {loading && (
          <span className="mr-1.5 inline-block h-3 w-3 animate-spin rounded-full border border-current border-t-transparent" />
        )}
        {children}
      </button>
    );
  }
);
Button.displayName = 'Button';
