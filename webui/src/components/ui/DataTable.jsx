import './DataTable.css';

/**
 * 数据表格：用留白与柔底分区，不使用 1px 实线切割。
 * layout 为 grid-template-columns 字符串；窄屏在容器内横向滚动，不撑破页面。
 */
export default function DataTable({ layout, minWidth = 760, children, className = '', ...rest }) {
  return (
    <div className={`ui-table ${className}`.trim()} {...rest}>
      <div
        className="ui-table__scroll"
        style={{ '--table-cols': layout, '--table-min': `${minWidth}px` }}
      >
        {children}
      </div>
    </div>
  );
}

export function DataRow({ children, className = '', index = 0, ...rest }) {
  return (
    <div
      className={`ui-table__row ${className}`.trim()}
      style={{ '--stagger-index': index }}
      {...rest}
    >
      {children}
    </div>
  );
}

export function Cell({ label, children, className = '', mono = false }) {
  return (
    <div className={`ui-table__cell ${className}`.trim()}>
      {label ? <span className="ui-table__label">{label}</span> : null}
      <span className={`ui-table__value${mono ? ' ui-table__value--mono' : ''}`}>{children}</span>
    </div>
  );
}

/** 身份单元格：圆形图标 + 主标题 + 次标题。 */
export function IdentityCell({ icon: Icon, tone = 'indigo', title, subtitle, extra }) {
  return (
    <div className="ui-table__identity">
      {Icon ? (
        <span className={`ui-table__avatar ui-table__avatar--${tone}`} aria-hidden="true">
          <Icon size={17} strokeWidth={2} />
        </span>
      ) : null}
      <div className="ui-table__identity-text">
        <strong>{title}</strong>
        {subtitle ? <small>{subtitle}</small> : null}
        {extra}
      </div>
    </div>
  );
}
