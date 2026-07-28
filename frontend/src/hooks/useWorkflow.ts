import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

export interface WorkflowListItem {
  id: string;
  name: string;
  description: string;
  updated_at: number;
  is_favorite?: boolean;
  node_count?: number;
}

export interface WorkflowDetail {
  id: string;
  name: string;
  description: string;
  nodes: Array<{
    uuid: string;
    name: string;
    title: string;
    positionX: number;
    positionY: number;
    width?: number;
    height?: number;
    static_input_data: Record<string, unknown>;
    output_path?: string;
  }>;
  links: Array<{
    uuid: string;
    previous_node_uuid: string;
    output_field_name: string;
    next_node_uuid: string;
    input_field_name: string;
  }>;
  created_at: number;
  updated_at: number;
  last_run_id?: string | null;
  is_favorite?: boolean;
}

export interface WorkflowTemplate {
  id: string;
  name: string;
  description: string;
  nodes: WorkflowDetail['nodes'];
  links: WorkflowDetail['links'];
}

export function useWorkflows(tab: string = 'my', search: string = '') {
  return useQuery<WorkflowListItem[]>({
    queryKey: ['workflows', tab, search],
    queryFn: () => {
      const params = new URLSearchParams({ tab, search });
      return fetch(`/api/workflow/?${params}`).then(r => r.json());
    },
  });
}

export function useWorkflow(id: string | null) {
  return useQuery<WorkflowDetail>({
    queryKey: ['workflow', id],
    queryFn: () => fetch(`/api/workflow/${id}`).then(r => r.json()),
    enabled: !!id,
  });
}

export function useSaveWorkflow() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: {
      id?: string | null;
      name: string;
      description?: string;
      nodes: WorkflowDetail['nodes'];
      links: WorkflowDetail['links'];
    }) => {
      // 后端统一使用 POST /api/workflow/，通过 body 中是否含 id 区分创建/更新
      const body: Record<string, unknown> = {
        name: data.name,
        description: data.description || '',
        nodes: data.nodes,
        links: data.links,
      };
      if (data.id) {
        body.id = data.id;
      }
      return fetch('/api/workflow/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }).then(r => r.json());
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['workflows'] }),
  });
}

export function useDeleteWorkflow() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      fetch(`/api/workflow/${id}`, { method: 'DELETE' }).then(r => r.json()),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['workflows'] }),
  });
}

export function useWorkflowTemplates() {
  return useQuery<WorkflowTemplate[]>({
    queryKey: ['workflow-templates'],
    queryFn: () => fetch('/api/workflow/templates').then(r => r.json()),
  });
}

export function useCreateFromTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (templateId: string) => {
      return fetch('/api/workflow/from-template', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ template_id: templateId }),
      }).then(r => r.json());
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['workflows'] }),
  });
}

export function useToggleFavorite() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      return fetch(`/api/workflow/${id}/favorite`, {
        method: 'PUT',
      }).then(r => r.json());
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] });
    },
  });
}

export function useGetTemplates() {
  return useQuery<WorkflowTemplate[]>({
    queryKey: ['workflow-templates'],
    queryFn: () => fetch('/api/workflow/templates').then(r => r.json()),
  });
}

export function useCreateFromTemplateHook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (templateId: string) => {
      return fetch('/api/workflow/from-template', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ template_id: templateId }),
      }).then(r => r.json());
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['workflows'] }),
  });
}
