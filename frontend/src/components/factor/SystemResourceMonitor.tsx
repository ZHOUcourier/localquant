import { useEffect, useState } from 'react';
import { Cpu, MemoryStick, HardDrive, Zap } from 'lucide-react';

/** 后端 /api/system/resources 返回结构 */
interface Resources {
  cpu: { per_core: number[]; count: number; avg: number; freq_mhz: number | null };
  memory: {
    physical: { used: number; total: number; percent: number };
    virtual: { used: number; total: number; percent: number };
  };
  disk: {
    cache: number; outputs: number; experiments: number; factor_total: number;
    device: { total: number; used: number; free: number; percent: number };
  };
  gpu: { available: boolean; reason?: string; gpus?: { name: string; util: number; mem_used_mb: number; mem_total_mb: number; temperature: number | null }[] };
}

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let v = n / 1024;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v >= 100 ? 0 : 1)} ${units[i]}`;
}

/** 用量 → 颜色（低=绿, 中=琥珀, 高=红） */
function levelColor(pct: number): string {
  if (pct >= 85) return '#ff3b30';
  if (pct >= 60) return '#ff9f0a';
  return '#30d158';
}

const LABEL = 'text-[10px] uppercase tracking-wide text-[#9a9898]';
const SECTION = 'rounded-[4px] border border-[rgba(15,0,0,0.1)] bg-[#fdfcfc] p-3';

/** 水平占用条 */
function Bar({ percent, color }: { percent: number; color?: string }) {
  const p = Math.max(0, Math.min(100, percent));
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-[#f1eeee]">
      <div className="h-full rounded-full transition-[width] duration-500" style={{ width: `${p}%`, background: color || levelColor(p) }} />
    </div>
  );
}

/**
 * 系统资源监控（CPU 分核心 / 内存物理+虚拟 / 磁盘因子占用 / GPU）
 * — opencode 浅色风格，图形化直观展示，每 2s 轮询一次。
 */
export default function SystemResourceMonitor() {
  const [res, setRes] = useState<Resources | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const r = await fetch('/api/system/resources');
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = await r.json();
        if (alive) { setRes(data); setError(null); }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      }
    };
    tick();
    const id = setInterval(tick, 2000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  return (
    <div className="flex h-full flex-col gap-3 overflow-auto">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-[#201d1d]">系统资源</h2>
        <span className="flex items-center gap-1 text-[10px] text-[#9a9898]">
          <span className="h-1.5 w-1.5 rounded-full" style={{ background: error ? '#ff3b30' : '#30d158' }} />
          {error ? '连接中断' : '实时 · 2s'}
        </span>
      </div>

      {!res ? (
        <div className="flex flex-1 items-center justify-center text-xs text-[#646262]">
          {error ? `资源读取失败: ${error}` : '读取系统资源中...'}
        </div>
      ) : (
        <>
          {/* CPU：每核心竖条 */}
          <div className={SECTION}>
            <div className="mb-2 flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-xs font-medium text-[#201d1d]"><Cpu size={13} /> CPU</span>
              <span className="font-mono text-xs text-[#646262]">
                {res.cpu.count} 核 · 均 <span style={{ color: levelColor(res.cpu.avg) }}>{res.cpu.avg}%</span>
                {res.cpu.freq_mhz ? ` · ${(res.cpu.freq_mhz / 1000).toFixed(1)}GHz` : ''}
              </span>
            </div>
            <div className="flex items-end gap-1" style={{ height: 56 }}>
              {res.cpu.per_core.map((c, i) => (
                <div key={i} className="flex flex-1 flex-col items-center justify-end" title={`核心 ${i}: ${c}%`}>
                  <div className="flex w-full items-end justify-center overflow-hidden rounded-[2px] bg-[#f1eeee]" style={{ height: 44 }}>
                    <div className="w-full transition-[height] duration-500" style={{ height: `${Math.max(3, c)}%`, background: levelColor(c) }} />
                  </div>
                  <span className="mt-0.5 text-[9px] text-[#9a9898]">{i}</span>
                </div>
              ))}
            </div>
          </div>

          {/* 内存：物理 + 虚拟 */}
          <div className={SECTION}>
            <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-[#201d1d]"><MemoryStick size={13} /> 内存</div>
            <div className="space-y-2.5">
              <div>
                <div className="mb-1 flex items-center justify-between">
                  <span className={LABEL}>物理内存</span>
                  <span className="font-mono text-[10px] text-[#646262]">{fmtBytes(res.memory.physical.used)} / {fmtBytes(res.memory.physical.total)} · {res.memory.physical.percent}%</span>
                </div>
                <Bar percent={res.memory.physical.percent} />
              </div>
              <div>
                <div className="mb-1 flex items-center justify-between">
                  <span className={LABEL}>虚拟内存 (交换)</span>
                  <span className="font-mono text-[10px] text-[#646262]">{fmtBytes(res.memory.virtual.used)} / {fmtBytes(res.memory.virtual.total)} · {res.memory.virtual.percent}%</span>
                </div>
                <Bar percent={res.memory.virtual.percent} />
              </div>
            </div>
          </div>

          {/* 磁盘：因子运算占用 */}
          <div className={SECTION}>
            <div className="mb-2 flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-xs font-medium text-[#201d1d]"><HardDrive size={13} /> 磁盘 · 因子运算占用</span>
              <span className="font-mono text-sm font-semibold text-[#201d1d]">{fmtBytes(res.disk.factor_total)}</span>
            </div>
            {/* 占用构成条 */}
            {res.disk.factor_total > 0 && (
              <div className="mb-2 flex h-2 w-full overflow-hidden rounded-full bg-[#f1eeee]">
                {([['缓存', res.disk.cache, '#007aff'], ['产物', res.disk.outputs, '#bf5af2'], ['实验', res.disk.experiments, '#30d158']] as const).map(([, v, color], i) => (
                  <div key={i} style={{ width: `${(v / res.disk.factor_total) * 100}%`, background: color }} />
                ))}
              </div>
            )}
            <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10px] text-[#646262]">
              <span><span className="mr-1 inline-block h-2 w-2 rounded-[2px] align-middle" style={{ background: '#007aff' }} />缓存 {fmtBytes(res.disk.cache)}</span>
              <span><span className="mr-1 inline-block h-2 w-2 rounded-[2px] align-middle" style={{ background: '#bf5af2' }} />产物 {fmtBytes(res.disk.outputs)}</span>
              <span><span className="mr-1 inline-block h-2 w-2 rounded-[2px] align-middle" style={{ background: '#30d158' }} />实验 {fmtBytes(res.disk.experiments)}</span>
            </div>
            <div className="mt-1.5 text-[10px] text-[#9a9898]">本盘剩余 {fmtBytes(res.disk.device.free)} / {fmtBytes(res.disk.device.total)}</div>
          </div>

          {/* GPU */}
          <div className={SECTION}>
            <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-[#201d1d]"><Zap size={13} /> GPU</div>
            {res.gpu.available && res.gpu.gpus ? (
              <div className="space-y-2.5">
                {res.gpu.gpus.map((g, i) => (
                  <div key={i}>
                    <div className="mb-1 flex items-center justify-between">
                      <span className="text-[11px] text-[#424245]">{g.name}{g.temperature != null ? ` · ${g.temperature}°C` : ''}</span>
                      <span className="font-mono text-[10px] text-[#646262]">{fmtBytes(g.mem_used_mb * 1024 * 1024)} / {fmtBytes(g.mem_total_mb * 1024 * 1024)} · {g.util}%</span>
                    </div>
                    <Bar percent={g.util} />
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-[11px] leading-relaxed text-[#9a9898]">{res.gpu.reason || '未检测到 GPU'}</div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
