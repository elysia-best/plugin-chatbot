import './Tabs.css';

/**
 * 胶囊标签页：选中项以白底柔光浮起，未选中保持雾灰底。
 * items: [{ id, label, icon: Icon, count }]
 */
export default function Tabs({ items, value, onChange, className = '', ariaLabel = '视图切换' }) {
  return (
    <div className={`ui-tabs ${className}`.trim()} role="tablist" aria-label={ariaLabel}>
      {items.map((item) => {
        const Icon = item.icon;
        const active = item.id === value;
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={active}
            className={`ui-tabs__tab${active ? ' is-active' : ''}`}
            onClick={() => onChange(item.id)}
          >
            {Icon ? <Icon size={15} strokeWidth={2.1} aria-hidden="true" /> : null}
            <span>{item.label}</span>
            {item.count != null ? <span className="ui-tabs__count">{item.count}</span> : null}
          </button>
        );
      })}
    </div>
  );
}
