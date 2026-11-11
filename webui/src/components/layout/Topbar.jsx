import { RefreshCw } from 'lucide-react';
import Button from '../ui/Button.jsx';
import './Topbar.css';

/**
 * 上下文栏：左侧是当前区块的场景提示（页面大标题由 PageHeader 承担），
 * 右侧是连接状态与全局刷新，避免与页面标题重复。
 */
export default function Topbar({ item, refreshing, onRefresh, connected = true }) {
  return (
    <header className="topbar">
      <div className="topbar__context">
        <span className="topbar__dot-label" aria-hidden="true" />
        <span className="topbar__hint">{item.hint}</span>
      </div>
      <div className="topbar__actions">
        <span className={`topbar__connection${connected ? ' is-on' : ' is-off'}`}>
          <span className="topbar__dot" aria-hidden="true" />
          {connected ? '已连接' : '连接异常'}
        </span>
        <Button
          variant="soft"
          size="sm"
          icon={RefreshCw}
          onClick={onRefresh}
          disabled={refreshing}
          aria-label="刷新数据"
        >
          {refreshing ? '刷新中' : '刷新'}
        </Button>
      </div>
    </header>
  );
}
