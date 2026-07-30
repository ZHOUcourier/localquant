// SPDX-License-Identifier: GPL-3.0-or-later
// LocalQuant ComfyUI 扩展：为托管的 ComfyUI 前端补齐 localquant 专属能力
//
//  1. 启动清空官方默认 SD3 文生图示例图（localquant 无这些 comfy-core 节点，避免报错）
//  2. 每个节点：右键菜单 + 右侧「节点代码」侧边栏 → 查看/编辑 Python 源码、
//     ✦ AI 改写、ruff 语法检查（内联诊断）、网页全屏、保存（内置节点 fork 保护）
//  3. 底部面板「本机性能」：CPU/内存/磁盘/GPU 实时监控（2s 轮询 /api/system/resources）
//
// 与后端同源，直接调用 localquant API：
//   GET  /api/plugins/{class}/source   取源码 + is_custom
//   POST /api/plugins/lint             ruff 检查，返回诊断
//   POST /api/ai/node-code             AI 改写
//   POST /api/plugins/custom / PUT /api/plugins/custom/{class}   fork / 更新
//   GET  /api/system/resources         本机资源

async function jsonFetch(url, options) {
  const res = await fetch(url, options);
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new Error(body?.detail || `HTTP ${res.status}`);
  return body;
}

function mkBtn(text, color, outline) {
  const b = document.createElement('button');
  b.textContent = text;
  b.style.cssText = outline
    ? `padding:5px 12px;border:1px solid ${color}66;background:transparent;color:${color};border-radius:4px;cursor:pointer;font-size:12px;font-family:inherit`
    : `padding:5px 14px;border:none;background:${color};color:#fdfcfc;border-radius:4px;cursor:pointer;font-size:12px;font-family:inherit`;
  return b;
}

// comfy-core 图像生成节点集合：出现即判定为官方默认示例图（localquant 不含这些）
const CORE_NODE_TYPES = new Set([
  'KSampler', 'CLIPLoader', 'CLIPTextEncode', 'UNETLoader', 'VAELoader', 'VAEDecode',
  'EmptySD3LatentImage', 'ModelSamplingAuraFlow', 'SaveImage', 'EmptyLatentImage',
  'CheckpointLoaderSimple', 'KSamplerAdvanced',
]);

// ——————————————————————————————————————————————————————————————
// 可复用的「节点代码编辑器」：填充到任意容器（弹窗 / 侧边栏共用）
// 返回 { load(classType, displayName) } 供侧边栏切换选中节点时刷新
// ——————————————————————————————————————————————————————————————
function mountCodeEditor(root, { onRequestFullscreen, fullscreen } = {}) {
  root.style.cssText =
    'display:flex;flex-direction:column;height:100%;min-height:0;background:#fdfcfc;color:#201d1d;font-family:ui-monospace,Menlo,Monaco,Consolas,monospace';

  const hint = document.createElement('div');
  hint.style.cssText = 'flex:0 0 auto;padding:8px 12px;font-size:11px;line-height:1.6;color:#646262;background:#f8f7f7';
  hint.textContent = '选中一个节点以查看其代码';
  root.appendChild(hint);

  const ta = document.createElement('textarea');
  ta.spellcheck = false;
  ta.style.cssText =
    'flex:1 1 auto;min-height:180px;margin:10px 12px;padding:10px;font-family:inherit;font-size:12px;line-height:1.5;color:#201d1d;background:#f8f7f7;border:1px solid rgba(15,0,0,.12);border-radius:4px;outline:none;resize:none;white-space:pre;overflow:auto;tab-size:4';
  ta.disabled = true;
  // Tab 键插入 4 空格（IDE 手感）
  ta.addEventListener('keydown', (e) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const s = ta.selectionStart, en = ta.selectionEnd;
      ta.value = ta.value.slice(0, s) + '    ' + ta.value.slice(en);
      ta.selectionStart = ta.selectionEnd = s + 4;
    }
  });
  root.appendChild(ta);

  // 诊断区（ruff 结果）
  const diag = document.createElement('div');
  diag.style.cssText =
    'flex:0 0 auto;max-height:120px;overflow:auto;margin:0 12px;font-size:11px;line-height:1.6;color:#646262';
  root.appendChild(diag);

  const foot = document.createElement('div');
  foot.style.cssText =
    'flex:0 0 auto;display:flex;align-items:center;gap:8px;padding:10px 12px;border-top:1px solid rgba(15,0,0,.12);flex-wrap:wrap';
  const msg = document.createElement('span');
  msg.style.cssText = 'flex:1;min-width:80px;font-size:11px;color:#646262';
  const lintBtn = mkBtn('ruff 检查', '#0056b3', true);
  const aiBtn = mkBtn('✦ AI 改写', '#7c3aed', true);
  const saveBtn = mkBtn('保存', '#201d1d', false);
  foot.append(msg, lintBtn, aiBtn, saveBtn);
  if (onRequestFullscreen) {
    const fsBtn = mkBtn(fullscreen ? '退出全屏' : '全屏', '#646262', true);
    fsBtn.onclick = onRequestFullscreen;
    foot.appendChild(fsBtn);
  }
  root.appendChild(foot);

  let classType = null;
  let isCustom = false;

  async function load(ct, displayName) {
    classType = ct;
    diag.textContent = '';
    if (!ct) {
      ta.value = '';
      ta.disabled = true;
      hint.textContent = '选中一个节点以查看其代码';
      return;
    }
    ta.disabled = true;
    ta.value = '加载中...';
    msg.textContent = displayName || ct;
    try {
      const d = await jsonFetch(`/api/plugins/${encodeURIComponent(ct)}/source`);
      ta.value = d.source || '';
      ta.disabled = false;
      isCustom = !!d.is_custom;
      hint.innerHTML = isCustom
        ? '该节点为<b>自定义节点</b>，保存将<b>原地更新</b>其源码。'
        : '该节点为<b>内置节点</b>，保存将创建一个<b>「（改）」副本</b>（不改原节点）。';
    } catch (e) {
      ta.value = `无法读取源码：${e.message}`;
    }
  }

  function renderDiagnostics(diags, note) {
    diag.innerHTML = '';
    if (note) {
      const n = document.createElement('div');
      n.style.color = '#cc7f08';
      n.textContent = note;
      diag.appendChild(n);
    }
    if (!diags || diags.length === 0) {
      const ok = document.createElement('div');
      ok.style.color = '#248a3d';
      ok.textContent = '✓ ruff 检查通过，无问题';
      diag.appendChild(ok);
      return;
    }
    diags.forEach((d) => {
      const row = document.createElement('div');
      row.style.color = d.severity === 'error' ? '#d70015' : '#cc7f08';
      row.textContent = `L${d.line}:${d.column} ${d.code} ${d.message}`;
      diag.appendChild(row);
    });
  }

  lintBtn.onclick = async () => {
    if (!classType) return;
    lintBtn.disabled = true;
    msg.textContent = 'ruff 检查中…';
    try {
      const d = await jsonFetch('/api/plugins/lint', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: ta.value }),
      });
      renderDiagnostics(d.diagnostics, d.note);
      msg.textContent = d.ok ? '检查通过' : `发现 ${d.diagnostics.length} 处问题`;
    } catch (e) {
      msg.textContent = `检查失败：${e.message}`;
    } finally {
      lintBtn.disabled = false;
    }
  };

  aiBtn.onclick = async () => {
    if (!classType) return;
    const instruction = window.prompt('用自然语言描述要如何修改该节点（结果填入编辑器，确认后再保存）：');
    if (!instruction || !instruction.trim()) return;
    aiBtn.disabled = true;
    msg.textContent = 'AI 改写中…';
    try {
      const d = await jsonFetch('/api/ai/node-code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: ta.value, instruction, node_name: classType }),
      });
      ta.value = d.source || ta.value;
      msg.textContent = 'AI 已生成，请检查后点「保存」';
    } catch (e) {
      msg.textContent = `AI 失败：${e.message}`;
    } finally {
      aiBtn.disabled = false;
    }
  };

  saveBtn.onclick = async () => {
    if (!classType) return;
    saveBtn.disabled = true;
    msg.textContent = '保存中…';
    try {
      let saved;
      if (isCustom) {
        saved = await jsonFetch(`/api/plugins/custom/${encodeURIComponent(classType)}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ source: ta.value }),
        });
      } else {
        saved = await jsonFetch('/api/plugins/custom', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ source: ta.value, base_name: classType }),
        });
      }
      await refreshNodeDefs();
      msg.textContent = `已保存：${saved?.display_name || saved?.name || '完成'}`;
    } catch (e) {
      msg.textContent = `保存失败：${e.message}`;
    } finally {
      saveBtn.disabled = false;
    }
  };

  return { load };
}

// 弹窗形式（右键菜单触发），支持网页全屏
function openCodeDialog({ classType, displayName }) {
  const mask = document.createElement('div');
  mask.style.cssText =
    'position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.45)';
  const box = document.createElement('div');
  const setBox = (fs) => {
    box.style.cssText = fs
      ? 'display:flex;flex-direction:column;position:fixed;inset:0;background:#fdfcfc;overflow:hidden'
      : 'display:flex;flex-direction:column;width:min(820px,92vw);height:min(80vh,720px);background:#fdfcfc;border:1px solid rgba(15,0,0,.12);border-radius:6px;overflow:hidden';
  };
  let fs = false;
  setBox(fs);
  mask.appendChild(box);

  const head = document.createElement('div');
  head.style.cssText =
    'flex:0 0 auto;display:flex;align-items:center;justify-content:space-between;padding:10px 14px;border-bottom:1px solid rgba(15,0,0,.12);background:#f1eeee;font-family:ui-monospace,Menlo,Monaco,Consolas,monospace';
  const title = document.createElement('span');
  title.style.cssText = 'font-size:13px;font-weight:600;color:#201d1d';
  title.textContent = `节点代码 · ${displayName || classType}`;
  const x = document.createElement('button');
  x.textContent = '✕';
  x.style.cssText = 'border:none;background:transparent;color:#646262;cursor:pointer;font-size:14px';
  x.onclick = () => mask.remove();
  head.append(title, x);
  box.appendChild(head);

  const body = document.createElement('div');
  body.style.cssText = 'flex:1 1 auto;min-height:0;display:flex';
  box.appendChild(body);

  const editor = mountCodeEditor(body, {
    fullscreen: false,
    onRequestFullscreen: () => {
      fs = !fs;
      setBox(fs);
      box.appendChild(head); // 保持头在前
      box.insertBefore(head, body);
    },
  });
  editor.load(classType, displayName);
  document.body.appendChild(mask);
}

async function refreshNodeDefs() {
  try {
    const app = window.comfyAPI?.app?.app;
    const api = window.comfyAPI?.api?.api;
    if (app?.registerNodesFromDefs && api?.getNodeDefs) {
      await app.registerNodesFromDefs(await api.getNodeDefs());
    }
  } catch (e) {
    console.warn('[LocalQuant] 刷新节点定义失败（可手动刷新页面）', e);
  }
}

// ——————————————————————————————————————————————————————————————
// 本机性能实时监控（底部面板 tab）
// ——————————————————————————————————————————————————————————————
function fmtBytes(n) {
  if (!n || n < 1024) return `${n || 0} B`;
  const u = ['KB', 'MB', 'GB', 'TB'];
  let v = n / 1024, i = 0;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v >= 100 ? 0 : 1)} ${u[i]}`;
}
function levelColor(p) { return p >= 85 ? '#ff3b30' : p >= 60 ? '#ff9f0a' : '#30d158'; }
function bar(label, detail, pct) {
  const p = Math.max(0, Math.min(100, pct || 0));
  return `<div style="margin-bottom:8px"><div style="display:flex;justify-content:space-between;font-size:11px;color:#646262;margin-bottom:3px"><span>${label}</span><span>${detail}</span></div><div style="height:6px;background:#f1eeee;border-radius:3px;overflow:hidden"><div style="height:100%;width:${p}%;background:${levelColor(p)};transition:width .4s"></div></div></div>`;
}
function mountSystemMonitor(el) {
  el.style.cssText = 'height:100%;overflow:auto;padding:12px 14px;background:#fdfcfc;color:#201d1d;font-family:ui-monospace,Menlo,Monaco,Consolas,monospace';
  const inner = document.createElement('div');
  el.appendChild(inner);
  let timer = null;
  async function tick() {
    try {
      const r = await jsonFetch('/api/system/resources');
      const cpu = bar('CPU', `${r.cpu.count} 核 · 均 ${r.cpu.avg}%`, r.cpu.avg);
      const mem = bar('物理内存', `${fmtBytes(r.memory.physical.used)} / ${fmtBytes(r.memory.physical.total)} · ${r.memory.physical.percent}%`, r.memory.physical.percent);
      const swap = bar('虚拟内存', `${fmtBytes(r.memory.virtual.used)} / ${fmtBytes(r.memory.virtual.total)} · ${r.memory.virtual.percent}%`, r.memory.virtual.percent);
      const disk = `<div style="font-size:11px;color:#646262;margin:8px 0 3px">磁盘 · 因子运算占用 <b style="color:#201d1d">${fmtBytes(r.disk.factor_total)}</b>（缓存 ${fmtBytes(r.disk.cache)} · 产物 ${fmtBytes(r.disk.outputs)} · 实验 ${fmtBytes(r.disk.experiments)}）· 本盘剩余 ${fmtBytes(r.disk.device.free)}</div>`;
      let gpu = '';
      if (r.gpu?.available && r.gpu.gpus) {
        gpu = r.gpu.gpus.map((g) => bar(`GPU ${g.name}`, `${fmtBytes(g.mem_used_mb * 1048576)} / ${fmtBytes(g.mem_total_mb * 1048576)} · ${g.util}%`, g.util)).join('');
      } else {
        gpu = `<div style="font-size:11px;color:#9a9898;margin-top:6px">${r.gpu?.reason || '未检测到 GPU'}</div>`;
      }
      inner.innerHTML = cpu + mem + swap + disk + gpu;
    } catch (e) {
      inner.innerHTML = `<div style="font-size:11px;color:#ff3b30">资源读取失败：${e.message}</div>`;
    }
  }
  tick();
  timer = setInterval(tick, 2000);
  // 元素被移除时停止轮询
  const obs = new MutationObserver(() => {
    if (!document.body.contains(el)) { clearInterval(timer); obs.disconnect(); }
  });
  obs.observe(document.body, { childList: true, subtree: true });
}

// ——————————————————————————————————————————————————————————————
// 选中节点 → 取 class_type
// ——————————————————————————————————————————————————————————————
function selectedNodeType(app) {
  const sel = app?.canvas?.selected_nodes;
  if (!sel) return null;
  const node = Object.values(sel)[0];
  return node ? { type: node.type || node.comfyClass, title: node.title } : null;
}

function whenReady(cb, tries = 0) {
  const app = window.comfyAPI?.app?.app;
  if (app?.registerExtension) return cb(app);
  if (tries > 120) return;
  setTimeout(() => whenReady(cb, tries + 1), 100);
}

whenReady((app) => {
  app.registerExtension({
    name: 'localquant.NodeTools',
    // 底部面板：本机性能实时监控
    bottomPanelTabs: [
      {
        id: 'localquant-sysmon',
        title: '本机性能',
        type: 'custom',
        render: (el) => mountSystemMonitor(el),
      },
    ],
    // 启动后清空官方默认 SD3 示例图（localquant 无这些 comfy-core 节点）
    setup() {
      try {
        const nodes = app.graph?._nodes || [];
        const looksLikeDefault = nodes.length > 0 && nodes.some((n) => CORE_NODE_TYPES.has(n.type));
        const hasLocalquant = nodes.some((n) => !CORE_NODE_TYPES.has(n.type) && window.comfyAPI?.app?.app);
        if (looksLikeDefault && !hasLocalquant) {
          app.graph.clear();
          app.graph.setDirtyCanvas?.(true, true);
          console.info('[LocalQuant] 已清空官方默认示例图，从空白画布开始');
        }
      } catch (e) {
        console.warn('[LocalQuant] 清空默认图失败', e);
      }

      // 右侧「节点代码」侧边栏：跟随选中节点
      try {
        app.extensionManager?.registerSidebarTab?.({
          id: 'localquant-node-code',
          icon: 'mdi mdi-code-braces',
          title: '节点代码',
          tooltip: '查看/编辑选中节点的代码（AI 改写 · ruff 检查）',
          type: 'custom',
          render: (el) => {
            el.innerHTML = '';
            const wrap = document.createElement('div');
            wrap.style.cssText = 'height:100%;min-height:360px;display:flex';
            el.appendChild(wrap);
            let curType = null;
            let curTitle = null;
            const editorApi = mountCodeEditor(wrap, {
              // 侧栏的“全屏”：用当前选中节点弹出可全屏的代码窗
              onRequestFullscreen: () => {
                if (curType) openCodeDialog({ classType: curType, displayName: curTitle || curType });
              },
            });
            // 轮询选中节点变化，切换代码
            const poll = setInterval(() => {
              if (!document.body.contains(el)) { clearInterval(poll); return; }
              const sel = selectedNodeType(app);
              const t = sel?.type || null;
              if (t !== curType) {
                curType = t;
                curTitle = sel?.title || t;
                editorApi.load(t, curTitle);
              }
            }, 700);
          },
        });
      } catch (e) {
        console.warn('[LocalQuant] 注册节点代码侧边栏失败', e);
      }
    },
    // 每个节点右键菜单加入代码/AI 入口
    beforeRegisterNodeDef(nodeType, nodeData) {
      const classType = nodeData?.name;
      const displayName = nodeData?.display_name || classType;
      const orig = nodeType.prototype.getExtraMenuOptions;
      nodeType.prototype.getExtraMenuOptions = function (canvas, options) {
        const r = orig?.apply(this, arguments);
        options.push(
          { content: '📝 查看 / 编辑节点代码', callback: () => openCodeDialog({ classType, displayName }) },
          { content: '✦ AI 改写节点代码', callback: () => openCodeDialog({ classType, displayName }) },
        );
        return r;
      };
    },
  });
  console.info('[LocalQuant] 节点代码/AI/性能监控 扩展已加载');
});
