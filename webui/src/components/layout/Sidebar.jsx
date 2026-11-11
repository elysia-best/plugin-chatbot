import { ChevronRight, LogOut, Sparkles } from 'lucide-react';
import { NAV_GROUPS, NAV_ITEMS } from '../../lib/nav.js';
import './Sidebar.css';

/** 侧边栏：浮起的柔光卡片，分组导航 + 服务状态 + 退出。 */
export default function Sidebar({ page, onNavigate, onLogout, mode, connected = true }) {
  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <span className="sidebar__mark" aria-hidden="true">
          <Sparkles size={18} strokeWidth={2.1} />
        </span>
        <div className="sidebar__brand-text">
          <strong>Chatbot</strong>
          <span>control room</span>
        </div>
      </div>

      <nav className="sidebar__nav" aria-label="主导航">
        {NAV_GROUPS.map((group) => {
          const items = NAV_ITEMS.filter((item) => item.group === group.id);
          if (!items.length) return null;
          return (
            <div className="sidebar__group" key={group.id}>
              <span className="sidebar__caption">{group.label}</span>
              {items.map((item) => {
                const Icon = item.icon;
                const active = page === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    className={`nav-item${active ? ' is-active' : ''}`}
                    aria-current={active ? 'page' : undefined}
                    onClick={() => onNavigate(item.id)}
                  >
                    <span className={`nav-item__icon nav-item__icon--${item.tone}`} aria-hidden="true">
                      <Icon size={16} strokeWidth={2.1} />
                    </span>
                    <span className="nav-item__label">{item.label}</span>
                    <ChevronRight className="nav-item__arrow" size={14} aria-hidden="true" />
                  </button>
                );
              })}
            </div>
          );
        })}
      </nav>

      <div className="sidebar__foot">
        <div className={`sidebar__status${connected ? '' : ' is-off'}`}>
          <span className="sidebar__status-dot" aria-hidden="true" />
          <div>
            <strong>{connected ? '服务在线' : '连接异常'}</strong>
            <small>{mode === 'agent' ? 'Agent 模式' : 'Chat 模式'} · Alconna bridge</small>
          </div>
        </div>
        <button type="button" className="sidebar__logout" onClick={onLogout}>
          <LogOut size={15} />
          <span>退出控制台</span>
        </button>
      </div>
    </aside>
  );
}
