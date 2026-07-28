import React from 'react';
import { cn } from '@/lib/utils';

export interface Column<T> {
  key: string;
  title: React.ReactNode;
  dataIndex: keyof T;
  width?: string | number;
  render?: (value: T[keyof T], record: T, index: number) => React.ReactNode;
}

export interface TableProps<T> extends React.HTMLAttributes<HTMLTableElement> {
  columns: Column<T>[];
  dataSource: T[];
  rowKey?: keyof T | ((record: T) => string);
  onRow?: (record: T, index: number) => React.HTMLAttributes<HTMLTableRowElement>;
}

function TableInner<T extends object>(
  { columns, dataSource, rowKey = 'id' as keyof T, onRow, className, ...props }: TableProps<T>,
  ref: React.ForwardedRef<HTMLTableElement>
) {
  const getRowKey = (record: T, index: number): string => {
    if (typeof rowKey === 'function') return rowKey(record);
    return String(record[rowKey] ?? index);
  };

  return (
    <table
      ref={ref}
      className={cn('w-full border-collapse text-sm', className)}
      {...props}
    >
      <thead>
        <tr className="bg-[#21262d]">
          {columns.map((col) => (
            <th
              key={col.key}
              className="border-b border-[#30363d] px-3 py-2 text-left text-xs font-medium text-[#808080]"
              style={{ width: col.width }}
            >
              {col.title}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {dataSource.map((record, rowIndex) => (
          <tr
            key={getRowKey(record, rowIndex)}
            className="border-b border-[#30363d] transition-colors hover:bg-[#2d333b]"
            {...onRow?.(record, rowIndex)}
          >
            {columns.map((col) => (
              <td key={col.key} className="px-3 py-2 text-[#eeeeee]">
                {col.render
                  ? col.render(record[col.dataIndex], record, rowIndex)
                  : String(record[col.dataIndex] ?? '')}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export const Table = React.forwardRef(TableInner) as <T extends object>(
  props: TableProps<T> & { ref?: React.Ref<HTMLTableElement> }
) => React.ReactElement;

(Table as unknown as { displayName: string }).displayName = 'Table';
