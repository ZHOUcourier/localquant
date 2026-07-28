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
  resetStatuses: () => void;
  setRunning: (running: boolean) => void;

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

  resetStatuses: () => set({ nodeStatuses: {}, isRunning: false }),

  setRunning: (running) => set({ isRunning: running }),

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
    set((state) => ({ edges: addEdge(connection, state.edges), isDirty: true })),
}));
