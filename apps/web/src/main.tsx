import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import { mockMode, ensureUiSession } from './api';
import './theme.css';
import './app.css';

const qc = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 15_000 } },
});

async function start() {
  // UI session 引导：先 GET /api/v1/ui/session 换取会话 cookie，再渲染并发起数据查询
  if (!mockMode) {
    await ensureUiSession();
  }
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <QueryClientProvider client={qc}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </StrictMode>,
  );
}

void start();
