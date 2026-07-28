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
  primary: 'bg-[#fab283] text-[#0a0a0a] border border-[#fab283] hover:bg-[#f5a06a] disabled:bg-[#555555] disabled:border-[#555555] disabled:text-[#808080]',
  secondary: 'bg-[#21262d] text-[#eeeeee] border border-[#30363d] hover:bg-[#2d333b] disabled:bg-[#161b22] disabled:text-[#555555] disabled:border-[#30363d]',
  ghost: 'bg-transparent text-[#eeeeee] border border-transparent hover:bg-[#21262d] disabled:text-[#555555]',
  danger: 'bg-[#e06c75] text-[#0a0a0a] border border-[#e06c75] hover:bg-[#c85a63] disabled:bg-[#555555] disabled:border-[#555555] disabled:text-[#808080]',
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
