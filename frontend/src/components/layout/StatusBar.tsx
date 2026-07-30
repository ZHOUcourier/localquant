import { useEffect, useState } from 'react';

/** 后端 /api/data/ticker 返回结构 */
interface Quote {
  name: string;
  code: string;
  price?: number;
  change?: number;
  pct?: number;
  amount?: number;
  date?: string;
  source: 'qmt' | 'cache' | 'none';
}

interface TickerResponse {
  qmt_connected: boolean;
  quotes: Quote[];
}

/** 成交额（元）→ 「xxxx亿」 */
function fmtAmount(amount?: number): string {
  if (!amount || amount <= 0) return '';
  return `${(amount / 1e8).toFixed(0)}亿`;
}

/** A 股配色：红涨绿跌 */
function pctColor(pct?: number): string {
  if (pct == null) return '#9a9898';
  if (pct > 0) return '#ff3b30';
  if (pct < 0) return '#30d158';
  return '#646262';
}

/** 资讯源标识 → 展示名 */
const NEWS_SOURCE_LABELS: Record<string, string> = {
  eastmoney: '东财快讯',
  sina: '新浪7×24',
};

/**
 * 底部状态栏（对标券商终端底栏）：
 * 上行滚动资讯（真实快讯源：东财/新浪 7×24，不可用时明确提示）、
 * 下行指数行情（QMT 实时优先，未连接回退本地缓存收盘价）+ QMT 连接状态。
 */
export default function StatusBar() {
  const [ticker, setTicker] = useState<TickerResponse | null>(null);
  const [news, setNews] = useState<string[]>([]);
  const [newsSource, setNewsSource] = useState('');
  const [newsError, setNewsError] = useState<string | null>(null);

  // 行情：15s 轮询
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const r = await fetch('/api/data/ticker');
        if (!r.ok) return;
        const data = await r.json();
        if (alive) setTicker(data);
      } catch {
        /* 后端离线时静默，Layout 已有离线提示条 */
      }
    };
    tick();
    const id = setInterval(tick, 15000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  // 资讯：60s 轮询（后端同样有 60s 缓存）
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r = await fetch('/api/data/news');
        if (!r.ok) return;
        const data = await r.json();
        if (alive) {
          setNews(data.items || []);
          setNewsSource(data.source || '');
          setNewsError(data.error || null);
        }
      } catch {
        /* ignore */
      }
    };
    load();
    const id = setInterval(load, 60000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const quotes = ticker?.quotes?.filter((q) => q.source !== 'none') ?? [];
  const cacheMode = quotes.length > 0 && quotes.every((q) => q.source === 'cache');
  const newsText = news.join('　　');

  return (
    <div
      className="shrink-0 select-none font-mono"
      style={{
        borderTop: '1px solid rgba(15,0,0,0.12)',
        background: '#f8f7f7',
        fontVariantNumeric: 'tabular-nums',
      }}
    >
      {/* 第一行：资讯滚动 */}
      <div
        className="flex items-center gap-2 overflow-hidden px-3"
        style={{ height: 24, borderBottom: '1px solid rgba(15,0,0,0.08)' }}
      >
        <span
          className="shrink-0 rounded-[3px] px-1.5 text-[10px] font-semibold"
          style={{ background: 'rgba(0,122,255,0.1)', color: '#0056b3', lineHeight: '16px' }}
        >
          资讯{NEWS_SOURCE_LABELS[newsSource] ? ` · ${NEWS_SOURCE_LABELS[newsSource]}` : ''}
        </span>
        <div className="relative flex-1 overflow-hidden" style={{ height: 24 }}>
          {news.length > 0 ? (
            <div className="statusbar-marquee absolute whitespace-nowrap text-[11px] text-[#424245]" style={{ lineHeight: '24px' }}>
              {newsText}　　{newsText}
            </div>
          ) : (
            <span className="text-[11px] text-[#9a9898]" style={{ lineHeight: '24px' }}>
              {newsError || '资讯加载中...'}
            </span>
          )}
        </div>
      </div>

      {/* 第二行：指数行情 + QMT 状态 */}
      <div className="flex items-center gap-4 overflow-x-auto px-3" style={{ height: 26 }}>
        {quotes.length === 0 && (
          <span className="text-[11px] text-[#9a9898]">
            暂无行情数据 — QMT 未连接且本地无指数缓存，请到「数据中心」下载指数日线（如 000001.SH）
          </span>
        )}
        {quotes.map((q) => (
          <span key={q.code} className="flex shrink-0 items-baseline gap-1.5 text-[11px]" title={`${q.code}${q.source === 'cache' ? `（本地缓存 ${q.date || ''} 收盘）` : '（QMT 实时）'}`}>
            <span className="text-[#424245]">{q.name}</span>
            <span style={{ color: pctColor(q.pct), fontWeight: 600 }}>{q.price?.toFixed(2)}</span>
            <span style={{ color: pctColor(q.pct) }}>
              {q.change != null && q.change > 0 ? '+' : ''}{q.change?.toFixed(2)}
            </span>
            <span style={{ color: pctColor(q.pct) }}>
              {q.pct != null && q.pct > 0 ? '+' : ''}{q.pct?.toFixed(2)}%
            </span>
            {fmtAmount(q.amount) && <span className="text-[#9a9898]">{fmtAmount(q.amount)}</span>}
          </span>
        ))}
        <div className="flex-1" />
        {cacheMode && (
          <span className="shrink-0 text-[10px] text-[#cc7f08]">本地缓存收盘价（非实时）</span>
        )}
        <span className="flex shrink-0 items-center gap-1.5 text-[11px] text-[#646262]">
          <span
            className="inline-block h-1.5 w-1.5 rounded-full"
            style={{ background: ticker?.qmt_connected ? '#30d158' : '#9a9898' }}
          />
          {ticker?.qmt_connected ? 'QMT 已连接' : 'QMT 未连接'}
        </span>
      </div>
    </div>
  );
}
