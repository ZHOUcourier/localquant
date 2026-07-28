import { useState, useCallback } from 'react';
import Editor from '@monaco-editor/react';
import { Card, Tabs, Input, Button, ScrollArea } from '@/components/ui';
import type { TabItem } from '@/components/ui';

export interface FactorResult {
  dates: string[];
  stocks: string[];
  values: Record<string, Record<string, number>>;
}

interface FactorBuilderProps {
  onFactorComputed?: (result: FactorResult) => void;
}

const builderTabs: TabItem[] = [
  { key: 'formula', label: '公式模式' },
  { key: 'code', label: '代码模式' },
];

const defaultCode = `import pandas as pd
import numpy as np

def compute_factor(close: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
    """
    自定义因子计算函数
    :param close: 收盘价 DataFrame (index=date, columns=stocks)
    :param volume: 成交量 DataFrame
    :return: 因子值 DataFrame
    """
    # 示例: 5日动量
    ret = close.pct_change(5)
    return ret
`;

export default function FactorBuilder({ onFactorComputed }: FactorBuilderProps) {
  const [mode, setMode] = useState('formula');
  const [formula, setFormula] = useState('');
  const [code, setCode] = useState(defaultCode);
  const [pool, setPool] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [computing, setComputing] = useState(false);
  const [preview, setPreview] = useState<FactorResult | null>(null);

  const handleCompute = useCallback(async () => {
    setComputing(true);
    try {
      // 模拟因子计算结果（实际应调用后端 API）
      const dates = ['2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05', '2024-01-08'];
      const stocks = ['000001.SZ', '000002.SZ', '600000.SH', '600036.SH'];
      const values: Record<string, Record<string, number>> = {};
      for (const d of dates) {
        values[d] = {};
        for (const s of stocks) {
          values[d][s] = Math.round((Math.random() - 0.5) * 2 * 1000) / 1000;
        }
      }
      const result: FactorResult = { dates, stocks, values };
      setPreview(result);
      onFactorComputed?.(result);
    } finally {
      setComputing(false);
    }
  }, [onFactorComputed]);

  return (
    <Card title="因子构建器" className="h-full flex flex-col">
      <div className="flex flex-col gap-3">
        {/* 模式切换 */}
        <Tabs
          items={builderTabs}
          activeKey={mode}
          onChange={setMode}
        />

        {/* 公式模式 */}
        {mode === 'formula' && (
          <div className="flex flex-col gap-2">
            <label className="text-xs text-[#808080]">因子公式表达式</label>
            <Input
              placeholder="例: close / close.shift(5) - 1"
              value={formula}
              onChange={(e) => setFormula(e.target.value)}
            />
          </div>
        )}

        {/* 代码模式 */}
        {mode === 'code' && (
          <div className="flex flex-col gap-2">
            <label className="text-xs text-[#808080]">Python 代码</label>
            <div className="rounded-[4px] border border-[#30363d] overflow-hidden" style={{ height: 220 }}>
              <Editor
                height="220px"
                language="python"
                theme="vs-dark"
                value={code}
                onChange={(v) => setCode(v ?? '')}
                options={{
                  minimap: { enabled: false },
                  fontSize: 13,
                  lineNumbers: 'on',
                  scrollBeyondLastLine: false,
                  automaticLayout: true,
                  tabSize: 4,
                }}
              />
            </div>
          </div>
        )}

        {/* 参数区域 */}
        <div className="grid grid-cols-3 gap-2">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-[#808080]">股票池</label>
            <Input
              placeholder="留空=全市场"
              value={pool}
              onChange={(e) => setPool(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-[#808080]">起始日期</label>
            <Input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-[#808080]">结束日期</label>
            <Input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </div>
        </div>

        <Button variant="primary" loading={computing} onClick={handleCompute}>
          计算因子
        </Button>

        {/* 因子值预览 */}
        {preview && (
          <div className="flex flex-col gap-2">
            <label className="text-xs text-[#808080]">因子值预览</label>
            <ScrollArea maxHeight={200}>
              <table className="w-full border-collapse text-xs">
                <thead>
                  <tr className="bg-[#21262d]">
                    <th className="border-b border-[#30363d] px-2 py-1.5 text-left text-[#808080] sticky top-0 bg-[#21262d]">
                      日期
                    </th>
                    {preview.stocks.map((s) => (
                      <th key={s} className="border-b border-[#30363d] px-2 py-1.5 text-right text-[#808080] sticky top-0 bg-[#21262d]">
                        {s}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.dates.map((d) => (
                    <tr key={d} className="hover:bg-[#2d333b]">
                      <td className="border-b border-[#30363d] px-2 py-1 text-[#808080]">{d}</td>
                      {preview.stocks.map((s) => {
                        const v = preview.values[d]?.[s] ?? 0;
                        return (
                          <td
                            key={s}
                            className={`border-b border-[#30363d] px-2 py-1 text-right font-mono ${v > 0 ? 'text-[#7fd88f]' : v < 0 ? 'text-[#e06c75]' : 'text-[#eeeeee]'}`}
                          >
                            {v.toFixed(3)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </ScrollArea>
          </div>
        )}
      </div>
    </Card>
  );
}
