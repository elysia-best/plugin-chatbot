import { useEffect, useState } from 'react';
import AppShell from './components/layout/AppShell.jsx';
import LoginPage from './pages/LoginPage.jsx';
import OverviewPage from './pages/OverviewPage.jsx';
import AccountsPage from './pages/AccountsPage.jsx';
import PersonasPage from './pages/PersonasPage.jsx';
import GroupsPage from './pages/GroupsPage.jsx';
import InterfacesPage from './pages/InterfacesPage.jsx';
import LogsPage from './pages/LogsPage.jsx';
import MemoryPage from './pages/MemoryPage.jsx';
import MemesPage from './pages/MemesPage.jsx';
import { ConfirmProvider } from './components/feedback/ConfirmProvider.jsx';
import { ToastProvider } from './components/feedback/ToastProvider.jsx';
import { api, clearStoredToken, readStoredToken } from './lib/api.js';
import { findNavItem } from './lib/nav.js';

const PAGES = {
  overview: OverviewPage,
  accounts: AccountsPage,
  personas: PersonasPage,
  groups: GroupsPage,
  interfaces: InterfacesPage,
  memory: MemoryPage,
  memes: MemesPage,
  logs: LogsPage,
};

function Console() {
  const [token, setToken] = useState(() => readStoredToken());
  const [page, setPage] = useState('overview');
  const [snapshot, setSnapshot] = useState(null);
  const [roles, setRoles] = useState({ roles: [], active: null });
  const [tools, setTools] = useState([]);
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [notice, setNotice] = useState('');

  useEffect(() => {
    if (!token) return undefined;
    let alive = true;
    setRefreshing(true);
    Promise.all([api(token, '/status'), api(token, '/roles'), api(token, '/tools')])
      .then(([nextSnapshot, roleRows, toolRows]) => {
        if (!alive) return;
        setSnapshot(nextSnapshot);
        setRoles(roleRows);
        setTools(toolRows);
        setError('');
      })
      .catch((err) => {
        if (alive) setError(err?.message || '连接失败');
      })
      .finally(() => {
        if (alive) setRefreshing(false);
      });
    return () => {
      alive = false;
    };
  }, [token]);

  // 令牌失效或首次连接失败：清空本地令牌并说明原因，避免静默回到登录页。
  useEffect(() => {
    if (!token || snapshot || !error || refreshing) return;
    clearStoredToken();
    setNotice('令牌校验未通过，请重新输入访问令牌。');
    setToken('');
    setError('');
  }, [token, snapshot, error, refreshing]);

  async function refresh() {
    if (!token) return;
    setRefreshing(true);
    try {
      const [nextSnapshot, roleRows, toolRows] = await Promise.all([
        api(token, '/status'),
        api(token, '/roles'),
        api(token, '/tools'),
      ]);
      setSnapshot(nextSnapshot);
      setRoles(roleRows);
      setTools(toolRows);
      setError('');
    } catch (err) {
      setError(err?.message || '刷新失败');
    } finally {
      setRefreshing(false);
    }
  }

  function handleLogin(nextToken) {
    setNotice('');
    setToken(nextToken);
  }

  function logout() {
    clearStoredToken();
    setToken('');
    setSnapshot(null);
    setPage('overview');
  }

  if (!token || !snapshot) {
    return <LoginPage onLogin={handleLogin} notice={notice} />;
  }

  const navItem = findNavItem(page);
  const Page = PAGES[page] || OverviewPage;
  const pageProps = {
    token,
    snapshot,
    roles,
    tools,
    onRefresh: refresh,
    onRolesChange: setRoles,
    onNavigate: setPage,
  };

  return (
    <AppShell
      page={page}
      navItem={navItem}
      mode={snapshot.mode}
      error={error}
      refreshing={refreshing}
      onRefresh={refresh}
      onNavigate={setPage}
      onLogout={logout}
    >
      <Page {...pageProps} />
    </AppShell>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <ConfirmProvider>
        <Console />
      </ConfirmProvider>
    </ToastProvider>
  );
}
