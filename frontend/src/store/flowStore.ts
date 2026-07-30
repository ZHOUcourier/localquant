import { create } from 'zustand';
import {
  type Node,
  type Edge,
  type OnNodesChange,
  type OnEdgesChange,
  type OnConnect,
  applyNodeChanges,
  applyEdgeChanges,
  addEdge,
} from '@xyflow/react';

export type NodeStatus = 'pending' | 'running' | 'success' | 'failed';

/** 执行日志条目（由 useExecution 解析 SSE 事件后写入） */
export interface ExecutionLogEntry {
  status: 'running' | 'success' | 'failed' | 'info';
  level?: string;
  message: string;
  timestamp: string;
  node_uuid?: string;
  node_name?: string;
  duration_ms?: number;
}

interface FlowState {
  // 工作流数据
  workflowId: string | null;
  workflowName: string;
  nodes: Node[];
  edges: Edge[];

  // 选中状态
  selectedNodeId: string | null;

  // 运行状态
  isRunning: boolean;
  nodeStatuses: Record<string, NodeStatus>;
  /** 每节点执行耗时（ms），运行完成/失败后写入，节点头部展示徽标 */
  nodeDurations: Record<string, number>;
  /** 失败节点的错误信息，节点底部展示 */
  nodeErrors: Record<string, string>;
  currentRunId: string | null;
  /** 本次运行起止时间戳（ms），供工具栏计时器与总耗时展示 */
  runStartedAt: number | null;
  runFinishedAt: number | null;
  executionLogs: ExecutionLogEntry[];

  // 画布锁定（锁定后禁止拖拽/连线/增删节点）
  locked: boolean;
  setLocked: (locked: boolean) => void;

  // 脏状态追踪
  isDirty: boolean;

  // 工作流操作
  setWorkflow: (id: string, name: string, nodes: Node[], edges: Edge[]) => void;
  setWorkflowName: (name: string) => void;
  addNode: (node: Node) => void;
  updateNodeData: (nodeId: string, data: Partial<Node['data']>) => void;
  selectNode: (nodeId: string | null) => void;

  // 运行状态操作
  setNodeStatus: (nodeId: string, status: NodeStatus) => void;
  setNodeDuration: (nodeId: string, ms: number) => void;
  setNodeError: (nodeId: string, error: string) => void;
  setRunStartedAt: (ts: number | null) => void;
  setRunFinishedAt: (ts: number | null) => void;
  resetStatuses: () => void;
  setRunning: (running: boolean) => void;
  setCurrentRunId: (runId: string | null) => void;
  appendLog: (entry: ExecutionLogEntry) => void;
  clearLogs: () => void;

  // 脏状态操作
  markDirty: () => void;
  markClean: () => void;
  resetState: () => void;

  // React Flow 回调
  onNodesChange: OnNodesChange;
  onEdgesChange: OnEdgesChange;
  onConnect: OnConnect;
}

export const useFlowStore = create<FlowState>((set) => ({
  workflowId: null,
  workflowName: '未命名工作流',
  nodes: [],
  edges: [],

  selectedNodeId: null,

  isRunning: false,
  nodeStatuses: {},
  nodeDurations: {},
  nodeErrors: {},
  currentRunId: null,
  runStartedAt: null,
  runFinishedAt: null,
  executionLogs: [],

  locked: false,
  setLocked: (locked) => set({ locked }),

  isDirty: false,

  setWorkflow: (id, name, nodes, edges) =>
    set({ workflowId: id, workflowName: name, nodes, edges, isDirty: false, selectedNodeId: null }),

  setWorkflowName: (name) => set({ workflowName: name }),

  addNode: (node) =>
    set((state) => ({ nodes: [...state.nodes, node], isDirty: true })),

  updateNodeData: (nodeId, data) =>
    set((state) => ({
      nodes: state.nodes.map((n) =>
        n.id === nodeId ? { ...n, data: { ...n.data, ...data } } : n
      ),
      isDirty: true,
    })),

  selectNode: (nodeId) => set({ selectedNodeId: nodeId }),

  setNodeStatus: (nodeId, status) =>
    set((state) => ({
      nodeStatuses: { ...state.nodeStatuses, [nodeId]: status },
    })),

  setNodeDuration: (nodeId, ms) =>
    set((state) => ({
      nodeDurations: { ...state.nodeDurations, [nodeId]: ms },
    })),

  setNodeError: (nodeId, error) =>
    set((state) => ({
      nodeErrors: { ...state.nodeErrors, [nodeId]: error },
    })),

  setRunStartedAt: (ts) => set({ runStartedAt: ts }),

  setRunFinishedAt: (ts) => set({ runFinishedAt: ts }),

  resetStatuses: () =>
    set({
      nodeStatuses: {},
      nodeDurations: {},
      nodeErrors: {},
      isRunning: false,
      runStartedAt: null,
      runFinishedAt: null,
    }),

  setRunning: (running) => set({ isRunning: running }),

  setCurrentRunId: (runId) => set({ currentRunId: runId }),

  appendLog: (entry) =>
    set((state) => ({ executionLogs: [...state.executionLogs, entry] })),

  clearLogs: () => set({ executionLogs: [] }),

  markDirty: () => set({ isDirty: true }),

  markClean: () => set({ isDirty: false }),

  resetState: () =>
    set({
      workflowId: null,
      workflowName: '未命名工作流',
      nodes: [],
      edges: [],
      selectedNodeId: null,
      isRunning: false,
      nodeStatuses: {},
      nodeDurations: {},
      nodeErrors: {},
      currentRunId: null,
      runStartedAt: null,
      runFinishedAt: null,
      executionLogs: [],
      isDirty: false,
    }),

  onNodesChange: (changes) =>
    set((state) => {
      // 仅实质性变更才标记为脏：选中/尺寸测量等不算修改，
      // 否则打开工作流什么都没改也会弹未保存确认
      const meaningful = changes.some(
        (c) => c.type === 'add' || c.type === 'remove' || c.type === 'position' || c.type === 'replace'
      );
      return {
        nodes: applyNodeChanges(changes, state.nodes),
        ...(meaningful ? { isDirty: true } : {}),
      };
    }),

  onEdgesChange: (changes) =>
    set((state) => {
      const meaningful = changes.some(
        (c) => c.type === 'add' || c.type === 'remove' || c.type === 'replace'
      );
      return {
        edges: applyEdgeChanges(changes, state.edges),
        ...(meaningful ? { isDirty: true } : {}),
      };
    }),

  onConnect: (connection) =>
    set((state) =>
      state.locked
        ? {}
        : { edges: addEdge(connection, state.edges), isDirty: true }
    ),
}));
