import React, { useState } from 'react';
import { cn } from '@/lib/utils';

export interface TabItem {
  key: string;
  label: React.ReactNode;
  disabled?: boolean;
}

export interface TabsProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'onChange'> {
  items: TabItem[];
  activeKey?: string;
  defaultActiveKey?: string;
  onChange?: (key: string) => void;
}

export const Tabs = React.forwardRef<HTMLDivElement, TabsProps>(
  ({ items, activeKey, defaultActiveKey, onChange, className, ...props }, ref) => {
    const [internalKey, setInternalKey] = useState(defaultActiveKey ?? items[0]?.key ?? '');
    const currentKey = activeKey ?? internalKey;

    const handleClick = (key: string, disabled?: boolean) => {
      if (disabled) return;
      setInternalKey(key);
      onChange?.(key);
    };

    return (
      <div ref={ref} className={cn('flex flex-col', className)} {...props}>
        <div className="flex border-b border-[#30363d]">
          {items.map((item) => (
            <button
              key={item.key}
              type="button"
              className={cn(
                'relative px-3 py-2 text-sm transition-colors cursor-pointer',
                item.disabled
                  ? 'text-[#555555] cursor-not-allowed'
                  : currentKey === item.key
                  ? 'text-[#fab283]'
                  : 'text-[#808080] hover:text-[#eeeeee]'
              )}
              onClick={() => handleClick(item.key, item.disabled)}
            >
              {item.label}
              {currentKey === item.key && (
                <span className="absolute bottom-0 left-0 right-0 h-[2px] bg-[#fab283]" />
              )}
            </button>
          ))}
        </div>
      </div>
    );
  }
);
Tabs.displayName = 'Tabs';
