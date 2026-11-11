import Button from './Button.jsx';
import './PageHeader.css';

/**
 * 页面标题区：kicker + 大标题 + 说明 + 主行动。
 * 保持与设计规范的层级：display 级标题、airy 留白。
 */
export default function PageHeader({ kicker, title, description, action, onAction, actionIcon, children }) {
  return (
    <header className="ui-page-header">
      <div className="ui-page-header__text">
        {kicker ? <span className="kicker">{kicker}</span> : null}
        <h2 className="ui-page-header__title">{title}</h2>
        {description ? <p className="ui-page-header__description">{description}</p> : null}
      </div>
      {(action || children) && (
        <div className="ui-page-header__actions">
          {children}
          {action ? (
            <Button variant="primary" icon={actionIcon} onClick={onAction}>
              {action}
            </Button>
          ) : null}
        </div>
      )}
    </header>
  );
}
