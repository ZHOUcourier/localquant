import React from 'react';
import { cn } from '@/lib/utils';

export interface InputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'prefix'> {
  prefix?: React.ReactNode;
  suffix?: React.ReactNode;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, prefix, suffix, disabled, ...props }, ref) => {
    return (
      <div
        className={cn(
          'flex items-center rounded-[4px] border border-[#403b3b] bg-[#302c2c] transition-colors',
          'focus-within:border-[#007aff]',
          disabled && 'opacity-50 cursor-not-allowed'
        )}
      >
        {prefix && (
          <span className="pl-2 text-[#9a9898] flex-shrink-0">{prefix}</span>
        )}
        <input
          ref={ref}
          disabled={disabled}
          className={cn(
            'w-full bg-transparent px-3 py-1.5 text-sm text-[#fdfcfc] outline-none',
            'font-mono placeholder:text-[#6e6e73]',
            className
          )}
          {...props}
        />
        {suffix && (
          <span className="pr-2 text-[#9a9898] flex-shrink-0">{suffix}</span>
        )}
      </div>
    );
  }
);
Input.displayName = 'Input';
