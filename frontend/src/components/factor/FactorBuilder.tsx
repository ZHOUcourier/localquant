import { useState, useCallback } from 'react';
import { Card, Tabs, Input, Button, ScrollArea, CodeEditor, Dialog } from '@/components/ui';
import type { TabItem } from '@/components/ui';

export interface FactorResult {
  dates: string[];
  stocks: string[];
  /** {date: {stock: factor_value}} */
  values: Record<string, Record<string, number>>;
  /** {date: {stock: daily_return}} 用于 IC / 分层分析 */
  returnData: Record<string, Record<string, number>>;
  /** 用于标识该因子（相关性分析） */
  name: string;
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
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<FactorResult | null>(null);
  // AI 生成/修改因子（公式与代码模式共用，与工作流节点 ✦ AI 交互一致）
  const [showAI, setShowAI] = useState(false);
  const [aiInstruction, setAiInstruction] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  const handleAI = useCallback(async () => {
    if (!aiInstruction.trim()) return;
    setAiLoading(true);
    setAiError(null);
    try {
      const res = await fetch('/api/ai/factor-code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode,
          current: mode === 'formula' ? formula : code,
          instruction: aiInstruction,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      // 结果填入编辑器，由用户确认后自行点「计算因子」
      if (mode === 'formula') setFormula(data.content || '');
      else setCode(data.content || '');
      setShowAI(false);
      setAiInstruction('');
    } catch (e) {
      setAiError(e instanceof Error ? e.message : String(e));
    } finally {
      setAiLoading(false);
    }
  }, [aiInstruction, mode, formula, code]);

  const handleCompute = useCallback(async () => {
    setComputing(true);
    setError(null);
    try {
      // 调用后端基于本地真实行情数据计算因子
      const res = await fetch('/api/factor/compute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode,
          formula,
          code,
          stock_pool: pool
            .split(/[,，\s]+/)
            .map((s) => s.trim())
            .filter(Boolean),
          start_date: startDate,
          end_date: endDate,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `因子计算接口错误 (HTTP ${res.status})`);
      }
      const data = await res.json();
      const result: FactorResult = {
        dates: data.dates,
        stocks: data.stocks,
        values: data.factor_data,
        returnData: data.return_data,
        name: mode === 'formula' ? (formula || 'factor') : 'custom_factor',
      };
      setPreview(result);
      onFactorComputed?.(result);
    } catch (e) {
      const msg = e instanceof TypeError
        ? '无法连接后端服务 (http://localhost:8000)，请先运行 make dev 或 make dev-backend'
        : e instanceof Error ? e.message : String(e);
      setError(msg);
      setPreview(null);
    } finally {
      setComputing(false);
    }
  }, [mode, formula, code, pool, startDate, endDate, onFactorComputed]);

  // 预览仅展示最近 20 个交易日，避免渲染过大表格
  const previewDates = preview ? preview.dates.slice(-20) : [];

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
            <div className="flex items-center justify-between">
              <label className="text-xs text-[#646262]">因子公式表达式（可用变量: open/high/low/close/volume/amount, np, pd）</label>
              <button
                className="tb-btn"
                onClick={() => setShowAI(true)}
                title="用 AI 生成/修改因子公式（需先在设置中配置 AI）"
                style={{
                  border: '1px solid rgba(124,58,237,0.4)',
                  background: 'transparent',
                  color: '#7c3aed',
                  borderRadius: 4,
                  fontSize: 11,
                  fontWeight: 600,
                  padding: '2px 8px',
                  cursor: 'pointer',
                }}
              >
                ✦ AI
              </button>
            </div>
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
            <div className="flex items-center justify-between">
              <label className="text-xs text-[#646262]">Python 代码</label>
              <button
                className="tb-btn"
                onClick={() => setShowAI(true)}
                title="用 AI 生成/修改因子代码（需先在设置中配置 AI）"
                style={{
                  border: '1px solid rgba(124,58,237,0.4)',
                  background: 'transparent',
                  color: '#7c3aed',
                  borderRadius: 4,
                  fontSize: 11,
                  fontWeight: 600,
                  padding: '2px 8px',
                  cursor: 'pointer',
                }}
              >
                ✦ AI
              </button>
            </div>
            <CodeEditor
              value={code}
              onChange={setCode}
              language="python"
              height={220}
              title="因子代码编辑"
              fontSize={13}
            />
          </div>
        )}

        {/* 参数区域 */}
        <div className="grid grid-cols-3 gap-2">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-[#646262]">股票池</label>
            <Input
              placeholder="留空=全部已缓存股票"
              value={pool}
              onChange={(e) => setPool(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-[#646262]">起始日期</label>
            <Input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-[#646262]">结束日期</label>
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

        {/* 错误提示（真实后端错误，无模拟数据兜底） */}
        {error && (
          <div className="rounded-[4px] border border-[#ff3b30] bg-[#ff3b30]/10 px-3 py-2 font-mono text-xs text-[#ff3b30]">
            {error}
          </div>
        )}

        {/* 因子值预览 */}
        {preview && (
          <div className="flex flex-col gap-2">
            <label className="text-xs text-[#646262]">因子值预览（最近 {previewDates.length} 个交易日）</label>
            <ScrollArea maxHeight={200}>
              <table className="w-full border-collapse text-xs">
                <thead>
                  <tr className="bg-[#f8f7f7]">
                    <th className="border-b border-[rgba(15,0,0,0.12)] px-2 py-1.5 text-left text-[#646262] sticky top-0 bg-[#f8f7f7]">
                      日期
                    </th>
                    {preview.stocks.map((s) => (
                      <th key={s} className="border-b border-[rgba(15,0,0,0.12)] px-2 py-1.5 text-right text-[#646262] sticky top-0 bg-[#f8f7f7]">
                        {s}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {previewDates.map((d) => (
                    <tr key={d} className="hover:bg-[#f1eeee]">
                      <td className="border-b border-[rgba(15,0,0,0.12)] px-2 py-1 text-[#646262]">{d}</td>
                      {preview.stocks.map((s) => {
                        const v = preview.values[d]?.[s];
                        return (
                          <td
                            key={s}
                            className={`border-b border-[rgba(15,0,0,0.12)] px-2 py-1 text-right font-mono ${v != null && v > 0 ? 'text-[#30d158]' : v != null && v < 0 ? 'text-[#ff3b30]' : 'text-[#201d1d]'}`}
                          >
                            {v != null ? v.toFixed(3) : '-'}
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

      {/* AI 生成/修改因子弹窗 */}
      <Dialog
        open={showAI}
        onClose={() => !aiLoading && setShowAI(false)}
        title={mode === 'formula' ? 'AI 生成 / 修改因子公式' : 'AI 生成 / 修改因子代码'}
        className="w-[520px]"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowAI(false)} disabled={aiLoading}>
              取消
            </Button>
            <Button onClick={handleAI} loading={aiLoading} disabled={!aiInstruction.trim()}>
              {aiLoading ? '生成中...' : '生成并填入编辑器'}
            </Button>
          </>
        }
      >
        <div className="mb-2 text-[11px] leading-relaxed text-[#646262]">
          用自然语言描述想要的因子或修改要求，结果会填入编辑器，确认后再点「计算因子」。
        </div>
        {aiError && (
          <div className="mb-2 whitespace-pre-wrap font-mono text-[11px] text-[#ff3b30]">{aiError}</div>
        )}
        <textarea
          value={aiInstruction}
          onChange={(e) => setAiInstruction(e.target.value)}
          placeholder={mode === 'formula'
            ? '例：20 日动量截面排名因子；把当前公式改成对数收益版本'
            : '例：写一个 20 日反转因子；给当前代码加上去极值和标准化'}
          rows={5}
          autoFocus
          className="w-full resize-y rounded-[4px] border border-[rgba(15,0,0,0.12)] bg-[#f8f7f7] px-2.5 py-2 text-xs leading-relaxed text-[#201d1d] outline-none"
          style={{ fontFamily: 'inherit', boxSizing: 'border-box' }}
        />
      </Dialog>
    </Card>
  );
}
