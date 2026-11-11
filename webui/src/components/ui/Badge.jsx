import './Badge.css';

/** 运行状态徽标：薄荷色光点 + 文案。 */
export function StatusBadge({ enabled = true, onLabel = '运行中', offLabel = '已停止' }) {
  return (
    <span className={`ui-status ${enabled ? 'ui-status--on' : 'ui-status--off'}`}>
      <span className="ui-status__dot" aria-hidden="true" />
      {enabled ? onLabel : offLabel}
    </span>
  );
}

/** 轻量标签：用于平台名、关键词、工具名。 */
export function SoftTag({ children, tone = 'slate', title }) {
  return (
    <span className={`ui-tag ui-tag--${tone}`} title={title}>
      {children}
    </span>
  );
}

/** 计数徽标：附着在标签页或导航上。 */
export function CountBadge({ children, tone = 'indigo' }) {
  return <span className={`ui-count ui-count--${tone}`}>{children}</span>;
}

/** 状态胶囊：用于会话状态等中性信息。 */
export function StatePill({ children, tone = 'slate' }) {
  return <span className={`ui-pill ui-pill--${tone}`}>{children}</span>;
}
