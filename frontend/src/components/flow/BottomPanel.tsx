import React, { useState } from 'react';
import { Tabs } from '@/components/ui/Tabs';
import type { TabItem } from '@/components/ui/Tabs';
import { ExecutionLog } from './ExecutionLog';
import { ResultViewer } from './ResultViewer';
import { useFlowStore } from '@/store/flowStore';

const tabItems: TabItem[] = [
  { key: 'log', label: '执行日志' },
  { key: 'output', label: '节点输出' },
];

export const BottomPanel: React.FC = () => {
  const [expanded, setExpanded] = useState(false);
  const [activeTab, setActiveTab] = useState('log');
  const workflowId = useFlowStore((s) => s.workflowId);

  return (
    <div
      style={{
        flexShrink: 0,
        background: '#f1eeee',
        borderTop: '1px solid rgba(15,0,0,0.12)',
        display: 'flex',
        flexDirection: 'column',
        height: expanded ? 250 : 40,
        transition: 'height 0.2s ease',
        overflow: 'hidden',
      }}
    >
      {/* 标题栏 - 40px */}
      <div
        style={{
          height: 40,
          flexShrink: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          paddingLeft: 12,
          paddingRight: 12,
          cursor: 'pointer',
          userSelect: 'none',
        }}
        onClick={() => setExpanded((prev) => !prev)}
      >
        <Tabs
          items={tabItems}
          activeKey={activeTab}
          onChange={(key) => {
            setActiveTab(key);
            if (!expanded) setExpanded(true);
          }}
        />
        <span
          style={{
            color: '#646262',
            fontSize: 14,
            transform: expanded ? 'rotate(180deg)' : 'none',
            transition: 'transform 0.2s',
          }}
        >
          ▲
        </span>
      </div>

      {/* 内容区 */}
      {expanded && (
        <div style={{ flex: 1, overflow: 'hidden' }}>
          {activeTab === 'log' ? (
            <ExecutionLog workflowId={workflowId} />
          ) : (
            <ResultViewer />
          )}
        </div>
      )}
    </div>
  );
};
