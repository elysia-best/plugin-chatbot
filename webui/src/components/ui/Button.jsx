import './Button.css';

const ICON_SIZE = 16;

/**
 * 柔和按钮：靛蓝填充 / 柔底 / 幽灵 / 危险 / 圆形图标。
 * hover 上浮 4px、阴影扩大；按下回落并内凹。过渡 300ms。
 */
export default function Button({
  variant = 'primary',
  size = 'md',
  icon: Icon,
  iconRight: IconRight,
  loading = false,
  block = false,
  className = '',
  children,
  ...rest
}) {
  const classes = [
    'ui-button',
    `ui-button--${variant}`,
    `ui-button--${size}`,
    block ? 'ui-button--block' : '',
    children ? '' : 'ui-button--icon-only',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <button
      {...rest}
      type="button"
      className={classes}
      disabled={rest.disabled || loading}
      aria-busy={loading || undefined}
    >
      {loading ? (
        <span className="ui-button__spinner" aria-hidden="true" />
      ) : (
        Icon && <Icon size={ICON_SIZE} strokeWidth={2.1} aria-hidden="true" />
      )}
      {children ? <span className="ui-button__label">{children}</span> : null}
      {IconRight && !loading ? (
        <IconRight size={15} strokeWidth={2.1} aria-hidden="true" />
      ) : null}
    </button>
  );
}
