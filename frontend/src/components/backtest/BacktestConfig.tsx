import { useState } from 'react';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import Editor from '@monaco-editor/react';

export interface BacktestConfigData {
  signalCode: string;
  initialCapital: number;
  commissionRate: number;
  slippage: number;
  startDate: string;
  endDate: string;
  benchmark: string;
}

interface BacktestConfigProps {
  onRun: (config: BacktestConfigData) => void;
  loading?: boolean;
}

const defaultSignalCode = `# 定义信号函数
# 返回字典: {date_str: {code: signal_value}}
# signal_value > 0 做多, < 0 做空, = 0 空仓

def generate_signals(prices, **kwargs):
    """
    示例: 双均线交叉信号
    prices: DataFrame, columns=股票代码, index=日期
    """
    import pandas as pd
    
    short_window = kwargs.get('short_window', 5)
    long_window = kwargs.get('long_window', 20)
    
    signals = {}
    for code in prices.columns:
        price = prices[code].dropna()
        ma_short = price.rolling(short_window).mean()
        ma_long = price.rolling(long_window).mean()
        
        signal = (ma_short > ma_long).astype(int)
        signal[ma_short <= ma_long] = -1
        
        for date, sig in signal.items():
            date_str = date.strftime('%Y-%m-%d')
            if date_str not in signals:
                signals[date_str] = {}
            signals[date_str][code] = int(sig)
    
    return signals
`;

const benchmarkOptions = [
  { value: '000300.SH', label: '沪深300' },
  { value: '000905.SH', label: '中证500' },
  { value: '000016.SH', label: '上证50' },
  { value: '000852.SH', label: '中证1000' },
];

export function BacktestConfig({ onRun, loading }: BacktestConfigProps) {
  const [signalCode, setSignalCode] = useState(defaultSignalCode);
  const [initialCapital, setInitialCapital] = useState(1000000);
  const [commissionRate, setCommissionRate] = useState(0.001);
  const [slippage, setSlippage] = useState(0.001);
  const [startDate, setStartDate] = useState('2023-01-01');
  const [endDate, setEndDate] = useState('2024-12-31');
  const [benchmark, setBenchmark] = useState('000300.SH');

  const handleRun = () => {
    onRun({
      signalCode,
      initialCapital,
      commissionRate,
      slippage,
      startDate,
      endDate,
      benchmark,
    });
  };

  return (
    <div className="flex flex-col gap-4 h-full">
      {/* 信号定义 */}
      <Card title="信号定义" className="flex-1 min-h-0 flex flex-col">
        <div className="flex-1 min-h-[240px] rounded border border-[#30363d] overflow-hidden">
          <Editor
            height="100%"
            defaultLanguage="python"
            value={signalCode}
            onChange={(v) => setSignalCode(v ?? '')}
            theme="vs-dark"
            options={{
              minimap: { enabled: false },
              fontSize: 13,
              lineNumbers: 'on',
              scrollBeyondLastLine: false,
              wordWrap: 'on',
              padding: { top: 8 },
              fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
            }}
          />
        </div>
      </Card>

      {/* 回测参数 */}
      <Card title="回测参数">
        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-[#808080]">初始资金</label>
            <Input
              type="number"
              value={initialCapital}
              onChange={(e) => setInitialCapital(Number(e.target.value))}
              suffix="¥"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-[#808080]">手续费率</label>
            <Input
              type="number"
              step="0.0001"
              value={commissionRate}
              onChange={(e) => setCommissionRate(Number(e.target.value))}
              suffix="%"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-[#808080]">滑点</label>
            <Input
              type="number"
              step="0.0001"
              value={slippage}
              onChange={(e) => setSlippage(Number(e.target.value))}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-[#808080]">基准指数</label>
            <Select
              options={benchmarkOptions}
              value={benchmark}
              onChange={setBenchmark}
            />
          </div>
        </div>
      </Card>

      {/* 起止日期 */}
      <Card title="回测区间">
        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-[#808080]">开始日期</label>
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
      </Card>

      {/* 运行按钮 */}
      <Button
        variant="primary"
        size="lg"
        loading={loading}
        onClick={handleRun}
        className="w-full"
      >
        ▶ 运行回测
      </Button>
    </div>
  );
}
