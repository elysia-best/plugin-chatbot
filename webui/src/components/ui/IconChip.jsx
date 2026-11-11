import './IconChip.css';

/** 圆形图标块：主色 10% 底 + 图标用主色本身，无边框无阴影。 */
export default function IconChip({ icon: Icon, tone = 'indigo', size = 'md', className = '' }) {
  return (
    <span
      className={`ui-chip ui-chip--${tone} ui-chip--${size} ${className}`.trim()}
      aria-hidden="true"
    >
      <Icon size={size === 'lg' ? 22 : 17} strokeWidth={2} />
    </span>
  );
}
