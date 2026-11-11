import Sidebar from './Sidebar.jsx';
import Topbar from './Topbar.jsx';
import './AppShell.css';

/** 应用外壳：浮动侧边栏 + 内容列，内容列包含顶栏、全局提示与页面主体。 */
export default function AppShell({ navItem, page, mode, error, refreshing, onRefresh, onNavigate, onLogout, children }) {
  return (
    <div className="app-shell">
      <Sidebar
        page={page}
        mode={mode}
        connected={!error}
        onNavigate={onNavigate}
        onLogout={onLogout}
      />
      <main className="app-main">
        <Topbar item={navItem} refreshing={refreshing} onRefresh={onRefresh} connected={!error} />
        {error ? (
          <div className="app-alert" role="alert">
            <span className="app-alert__bar" aria-hidden="true" />
            {error}
          </div>
        ) : null}
        <div className="app-page" key={page}>
          {children}
        </div>
      </main>
    </div>
  );
}
