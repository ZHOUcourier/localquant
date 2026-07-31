# LocalQuant 前端

LocalQuant 的前端外壳：**Vue 3 + TypeScript + Vite**，OpenCode 浅色主题风格。
工作流编辑器页以 iframe 内嵌官方 ComfyUI 前端，其余页面（数据探索 / 因子研究 / QUBE / 策略库 / 实验管理 / 设置）为原生 Vue。

## 技术栈

- **框架**: Vue 3 (`<script setup>`) + TypeScript + Vite
- **样式**: Tailwind CSS v4（OpenCode 浅色主题，见 `DESIGN-opencode.ai.md`）
- **数据请求**: TanStack Vue Query
- **路由**: Vue Router
- **代码编辑**: Monaco（Python 补全 + ruff 内联诊断，`src/lib/monaco.ts`）
- **图表**: ECharts（`components/ui/VChart.vue`）
- **公式渲染**: KaTeX
- **Lint**: Oxlint（`.oxlintrc.json`）

## 开发

前端依赖后端 API（默认 `http://localhost:8000`，Vite 已代理 `/api` 与 `/comfy`）。
推荐在项目根目录用 `make dev` 一键起前后端；也可单独启动：

```bash
npm install
npm run dev        # http://localhost:5173（需后端已启动）
npm run build      # 产物输出到 dist/
npm run preview    # 预览构建产物
```

## 目录结构

```
src/
├── components/
│   ├── explore/    # 数据探索（概览 / SQL·AI / 扫描 / 截面 / 异常）
│   ├── factor/     # 因子研究（因子库 / 详情弹窗 / 综合报告）
│   ├── qube/       # QUBE 策略工作台（StrategyWorkbench）
│   ├── workflow/   # 节点代码 Monaco 弹窗等
│   ├── layout/     # 布局（侧栏 / 顶栏 / 状态栏）
│   └── ui/         # 通用组件（CodeEditor 全屏编辑器·ruff、VChart、Select 等）
├── composables/    # useWorkflow / usePlugins / usePresetFactors 等
├── lib/            # monaco.ts（编辑器接线）、utils.ts
├── pages/          # 页面（工作流 / 因子 / QUBE / 策略库 / 设置 等）
├── router.ts       # 路由表
└── main.ts         # 入口
```

> 工作流编辑器（`pages/WorkflowEditor.vue`）通过 iframe 承载 `/comfy/`，并经 postMessage
> 与外壳通信（因子分析报告弹窗、节点代码 Monaco 编辑弹窗均委托外壳呈现）。
