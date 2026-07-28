import React, { useState, useRef, useEffect } from 'react';
import { cn } from '@/lib/utils';

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'onChange' | 'defaultValue'> {
  options: SelectOption[];
  value?: string;
  defaultValue?: string;
  placeholder?: string;
  disabled?: boolean;
  onChange?: (value: string) => void;
}

export const Select = React.forwardRef<HTMLDivElement, SelectProps>(
  ({ options, value, defaultValue, placeholder = '请选择', disabled, onChange, className, ...props }, ref) => {
    const [open, setOpen] = useState(false);
    const [internalValue, setInternalValue] = useState(defaultValue ?? '');
    const containerRef = useRef<HTMLDivElement>(null);
    const currentValue = value ?? internalValue;

    const selectedOption = options.find((o) => o.value === currentValue);

    useEffect(() => {
      const handleClickOutside = (e: MouseEvent) => {
        if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
          setOpen(false);
        }
      };
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const handleSelect = (val: string, optionDisabled?: boolean) => {
      if (optionDisabled) return;
      setInternalValue(val);
      onChange?.(val);
      setOpen(false);
    };

    return (
      <div
        ref={(node) => {
          (containerRef as React.MutableRefObject<HTMLDivElement | null>).current = node;
          if (typeof ref === 'function') ref(node);
          else if (ref) (ref as React.MutableRefObject<HTMLDivElement | null>).current = node;
        }}
        className={cn('relative', className)}
        {...props}
      >
        <button
          type="button"
          className={cn(
            'flex w-full items-center justify-between rounded-[4px] border border-[#30363d] bg-[#21262d] px-3 py-1.5 text-sm text-[#eeeeee] transition-colors cursor-pointer',
            open && 'border-[#fab283]',
            disabled && 'opacity-50 cursor-not-allowed'
          )}
          disabled={disabled}
          onClick={() => setOpen(!open)}
        >
          <span className={cn(!selectedOption && 'text-[#555555]')}>
            {selectedOption ? selectedOption.label : placeholder}
          </span>
          <span className="ml-2 text-[#808080]">▾</span>
        </button>
        {open && (
          <div className="absolute z-50 mt-1 w-full rounded-[4px] border border-[#30363d] bg-[#161b22] py-1">
            {options.map((option) => (
              <div
                key={option.value}
                className={cn(
                  'cursor-pointer px-3 py-1.5 text-sm transition-colors',
                  option.disabled
                    ? 'text-[#555555] cursor-not-allowed'
                    : option.value === currentValue
                    ? 'bg-[#2d333b] text-[#fab283]'
                    : 'text-[#eeeeee] hover:bg-[#2d333b]'
                )}
                onClick={() => handleSelect(option.value, option.disabled)}
              >
                {option.label}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }
);
Select.displayName = 'Select';
