import { createRouter, createWebHistory } from 'vue-router'
import Layout from './components/layout/Layout.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: Layout,
      children: [
        { path: '', component: () => import('./pages/Dashboard.vue') },
        { path: 'data', component: () => import('./pages/DataCenter.vue') },
        // 旧路由兼容：数据探索已并入数据中心
        { path: 'explore', redirect: '/data' },
        { path: 'factor', component: () => import('./pages/FactorResearch.vue') },
        // 旧路由兼容：独立回测页已移除，回测能力由工作流回测节点提供
        { path: 'backtest', redirect: '/workflow' },
        { path: 'workflow', component: () => import('./pages/WorkflowList.vue') },
        // 工作流编辑器 = iframe 内嵌官方 ComfyUI 前端
        { path: 'workflow/:id', component: () => import('./pages/WorkflowEditor.vue') },
        // QUBE — 策略研究 AI Agent（对话创建策略）
        { path: 'qube', component: () => import('./pages/Qube.vue') },
        // 策略库（工作产出 / 落地成果）
        { path: 'strategies', component: () => import('./pages/StrategyLibrary.vue') },
        // 技能库（独立页：系统内置 + 自定义）
        { path: 'skills', component: () => import('./pages/Skills.vue') },
        { path: 'runs', component: () => import('./pages/RunCenter.vue') },
        { path: 'experiments', component: () => import('./pages/Experiments.vue') },
        { path: 'risk', component: () => import('./pages/RiskAnalysis.vue') },
        { path: 'settings', component: () => import('./pages/Settings.vue') },
      ],
    },
  ],
})
