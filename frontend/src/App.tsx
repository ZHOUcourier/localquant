import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Layout from './components/layout/Layout';
import Dashboard from './pages/Dashboard';
import DataExplore from './pages/DataExplore';
import FactorResearch from './pages/FactorResearch';
import BacktestPage from './pages/BacktestPage';
import WorkflowList from './pages/WorkflowList';
import WorkflowEditor from './pages/WorkflowEditor';
import Experiments from './pages/Experiments';
import DataManagement from './pages/DataManagement';
import Settings from './pages/Settings';

const queryClient = new QueryClient();

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Layout>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/explore" element={<DataExplore />} />
            <Route path="/factor" element={<FactorResearch />} />
            <Route path="/backtest" element={<BacktestPage />} />
            <Route path="/workflow" element={<WorkflowList />} />
            <Route path="/workflow/:id" element={<WorkflowEditor />} />
            <Route path="/experiments" element={<Experiments />} />
            <Route path="/data" element={<DataManagement />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </Layout>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
