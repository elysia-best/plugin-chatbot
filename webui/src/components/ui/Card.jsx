import './Card.css';

/**
 * 柔和卡片：白底、24px 圆角、无描边、彩色柔光阴影。
 * interactive 时 hover 上浮 8px、阴影转为靛蓝柔光（500ms）。
 */
export default function Card({
  as: Tag = 'section',
  interactive = false,
  bare = false,
  className = '',
  children,
  ...rest
}) {
  const classes = [
    'ui-card',
    interactive ? 'ui-card--interactive' : '',
    bare ? 'ui-card--bare' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <Tag className={classes} {...rest}>
      {children}
    </Tag>
  );
}

export function CardHeader({ title, description, actions, icon: Icon, tone = 'indigo' }) {
  return (
    <header className="ui-card__header">
      <div className="ui-card__heading">
        {Icon ? (
          <span className={`ui-card__icon ui-card__icon--${tone}`} aria-hidden="true">
            <Icon size={18} strokeWidth={2.1} />
          </span>
        ) : null}
        <div>
          <h3 className="ui-card__title">{title}</h3>
          {description ? <p className="ui-card__description">{description}</p> : null}
        </div>
      </div>
      {actions ? <div className="ui-card__actions">{actions}</div> : null}
    </header>
  );
}
