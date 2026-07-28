import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Layout from './components/layout/Layout';
import Dashboard from './pages/Dashboard';
import DataCenter from './pages/DataCenter';
import FactorResearch from './pages/FactorResearch';
import WorkflowList from './pages/WorkflowList';
import WorkflowEditor from './pages/WorkflowEditor';
import RunCenter from './pages/RunCenter';
import Experiments from './pages/Experiments';
import Settings from './pages/Settings';

const queryClient = new QueryClient();

// useBlocker 等 data API 需要 createBrowserRouter（data router），
// 使用 <BrowserRouter> 会导致 WorkflowEditor 抛异常白屏
const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'data', element: <DataCenter /> },
      // 旧路由兼容：数据探索已并入数据中心
      { path: 'explore', element: <Navigate to="/data" replace /> },
      { path: 'factor', element: <FactorResearch /> },
      // 旧路由兼容：独立回测页已移除，回测能力由工作流回测节点提供
      { path: 'backtest', element: <Navigate to="/workflow" replace /> },
      { path: 'workflow', element: <WorkflowList /> },
      { path: 'workflow/:id', element: <WorkflowEditor /> },
      { path: 'runs', element: <RunCenter /> },
      { path: 'experiments', element: <Experiments /> },
      { path: 'settings', element: <Settings /> },
    ],
  },
]);

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}

export default App;
